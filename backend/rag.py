from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TextIteratorStreamer
)

import torch
import os
import json
import re
from threading import Thread
from datetime import datetime


# ============================================================
# PERFORMANCE SETTINGS
# ============================================================

torch.set_num_threads(4)
torch.set_num_interop_threads(1)


# ============================================================
# CONFIGURATION
# ============================================================

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

TOP_K = 5

MAX_CONTEXT_CHARS = 4500

MAX_NEW_TOKENS = 256

# Similarity threshold
RELEVANCE_THRESHOLD = 0.40

# ------------------------------------------------------------
# ANSWER CONTROL
# ------------------------------------------------------------

# Absolute maximum answer size
MAX_ANSWER_WORDS = 80

# Once answer reaches this many words,
# stop at the next complete sentence.
START_SENTENCE_CHECK_WORDS = 50

# Repetition protection
MIN_REPEAT_WORDS = 4
MAX_SENTENCE_REPEAT = 1


# ============================================================
# PERSISTENT STORAGE
# ============================================================

PERSIST_DIR = "storage"

INDEX_PATH = os.path.join(
    PERSIST_DIR,
    "faiss_index.bin"
)

METADATA_PATH = os.path.join(
    PERSIST_DIR,
    "metadata.json"
)

os.makedirs(PERSIST_DIR, exist_ok=True)


# ============================================================
# GLOBAL VARIABLES
# ============================================================

chunks = []
chunk_sources = []
index = None


# ============================================================
# LOAD MODELS
# ============================================================

print("Loading embedding model...")

embedding_model = SentenceTransformer(
    EMBEDDING_MODEL,
    device="cpu"
)

print("Embedding model loaded.")

print("Loading language model...")

tokenizer = AutoTokenizer.from_pretrained(
    LLM_MODEL
)

model = AutoModelForCausalLM.from_pretrained(
    LLM_MODEL,
    torch_dtype=torch.float32
)

model.eval()

print("Language model loaded.")


# ============================================================
# PERSISTENCE
# ============================================================

def save_index():
    """
    Save FAISS index and document metadata.
    """

    global index
    global chunks
    global chunk_sources

    if index is None:
        return

    faiss.write_index(
        index,
        INDEX_PATH
    )

    metadata = {
        "chunks": chunks,
        "chunk_sources": chunk_sources,
        "saved_at": datetime.now().isoformat()
    }

    with open(
        METADATA_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            metadata,
            f,
            ensure_ascii=False
        )

    print("FAISS index saved.")


def load_index():
    """
    Load previously saved FAISS index.
    """

    global index
    global chunks
    global chunk_sources

    if not os.path.exists(INDEX_PATH):
        print("No saved FAISS index found.")
        return False

    if not os.path.exists(METADATA_PATH):
        print("No metadata file found.")
        return False

    try:

        print("Loading saved FAISS index...")

        index = faiss.read_index(
            INDEX_PATH
        )

        with open(
            METADATA_PATH,
            "r",
            encoding="utf-8"
        ) as f:

            metadata = json.load(f)

        # Use global variables
        chunks[:] = metadata.get(
            "chunks",
            []
        )

        chunk_sources[:] = metadata.get(
            "chunk_sources",
            []
        )

        print(
            f"Loaded {len(chunks)} document chunks."
        )

        return True

    except Exception as e:

        print(
            f"Error loading saved index: {e}"
        )

        index = None
        chunks = []
        chunk_sources = []

        return False


# ============================================================
# LOAD SAVED INDEX ON STARTUP
# ============================================================

load_index()


# ============================================================
# SIMPLE MESSAGE DETECTION
# ============================================================

def handle_simple_message(question):
    """
    Handle greetings and very simple conversational messages.
    """

    q = question.strip().lower()

    greetings = {
        "hi": "Hello! How can I help you?",
        "hello": "Hello! How can I help you?",
        "hey": "Hey! How can I help you?",
        "good morning": "Good morning! How can I help you?",
        "good afternoon": "Good afternoon! How can I help you?",
        "good evening": "Good evening! How can I help you?",
        "thanks": "You're welcome!",
        "thank you": "You're welcome!",
        "bye": "Goodbye!",
    }

    if q in greetings:
        return greetings[q]

    return None


# ============================================================
# TEXT CHUNKING
# ============================================================

def create_chunks(text):
    """
    Split document text into overlapping chunks.
    """

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    if not text:
        return []

    result = []

    start = 0

    text_length = len(text)

    while start < text_length:

        end = start + CHUNK_SIZE

        chunk = text[start:end]

        if chunk.strip():
            result.append(
                chunk.strip()
            )

        if end >= text_length:
            break

        start = end - CHUNK_OVERLAP

    return result


# ============================================================
# PROCESS PDF FILES
# ============================================================

def process_pdfs(pdf_paths, is_append=False):
    """
    Read PDFs, create chunks, generate embeddings,
    build FAISS index and save everything.
    """

    global chunks
    global chunk_sources
    global index

    print(f"{'Adding' if is_append else 'Processing'} PDFs...")

    if not is_append:
        chunks = []
        chunk_sources = []
        index = None

    new_chunks = []
    new_sources = []

    # --------------------------------------------------------
    # READ PDFs
    # --------------------------------------------------------

    for pdf_path in pdf_paths:
        filename = os.path.basename(pdf_path)
        print(f"Reading: {filename}")

        try:
            reader = PdfReader(pdf_path)
            for page_number, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text()
                except Exception as e:
                    print(f"Could not extract page {page_number}: {e}")
                    continue

                if not text:
                    continue

                page_chunks = create_chunks(text)
                for chunk in page_chunks:
                    new_chunks.append(chunk)
                    new_sources.append({
                        "source": filename,
                        "page": page_number
                    })

        except Exception as e:
            print(f"Error processing {pdf_path}: {e}")

    if not new_chunks:
        print("No text found in these PDFs.")
        return len(chunks)

    print(f"Created {len(new_chunks)} new chunks.")

    # --------------------------------------------------------
    # CREATE EMBEDDINGS
    # --------------------------------------------------------

    print("Creating embeddings for new chunks...")
    embeddings = embedding_model.encode(
        new_chunks,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True
    )
    embeddings = np.asarray(embeddings, dtype="float32")

    # --------------------------------------------------------
    # UPDATE FAISS INDEX
    # --------------------------------------------------------

    if index is None:
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)

    index.add(embeddings)

    # Append to globals
    chunks.extend(new_chunks)
    chunk_sources.extend(new_sources)

    print(f"FAISS index updated. Total vectors: {index.ntotal}")

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    save_index()
    print("PDF processing completed.")

    return len(chunks)


# ============================================================
# RETRIEVE RELEVANT CONTEXT
# ============================================================

def retrieve_context(question):
    """
    Search the FAISS index and determine whether
    the documents are relevant to the question.
    """

    global index

    if index is None:
        return "", [], 0.0, False

    if not chunks:
        return "", [], 0.0, False

    # --------------------------------------------------------
    # EMBED QUESTION
    # --------------------------------------------------------

    query_embedding = embedding_model.encode(
        [question],
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    query_embedding = np.asarray(
        query_embedding,
        dtype="float32"
    )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    k = min(
        TOP_K,
        len(chunks)
    )

    scores, indices = index.search(
        query_embedding,
        k
    )

    best_score = float(
        scores[0][0]
    )

    # --------------------------------------------------------
    # CHECK RELEVANCE
    # --------------------------------------------------------

    if best_score < RELEVANCE_THRESHOLD:

        print(
            f"Document not relevant "
            f"(score={best_score:.3f})"
        )

        return "", [], best_score, False

    # --------------------------------------------------------
    # BUILD CONTEXT
    # --------------------------------------------------------

    context_parts = []
    sources = []

    current_length = 0

    for score, idx in zip(
        scores[0],
        indices[0]
    ):

        if idx < 0:
            continue

        chunk = chunks[idx]

        source_info = chunk_sources[idx]

        remaining = (
            MAX_CONTEXT_CHARS -
            current_length
        )

        if remaining <= 0:
            break

        chunk_text = chunk[:remaining]

        context_parts.append(
            chunk_text
        )

        source_item = {
            "source": source_info.get(
                "source",
                "Unknown"
            ),
            "page": source_info.get(
                "page",
                None
            ),
            "snippet": chunk_text[:300]
        }

        sources.append(
            source_item
        )

        current_length += len(
            chunk_text
        )

    context = "\n\n".join(
        context_parts
    )

    return (
        context,
        sources,
        best_score,
        True
    )


# ============================================================
# PROMPT CONSTRUCTION
# ============================================================

def construct_full_prompt(
    question,
    context,
    history,
    is_rag
):
    """
    Build the prompt for TinyLlama.
    """

    system_prompt = """
You are a helpful educational AI assistant.

Give clear, accurate and concise answers.

Important rules:

1. Answer the user's actual question.
2. Do not repeat the same sentence.
3. Do not repeat the same phrase unnecessarily.
4. Do not invent information.
5. Do not add unnecessary introductions.
6. Do not write "Answer:" before the answer.
7. Do not output special tokens.
8. Keep the answer concise.
9. Explain concepts simply when appropriate.
"""

    if is_rag:

        document_instruction = """
The user is asking a question related to the provided
documents.

Use the document context as the main source when it is relevant.

You may also use general knowledge to explain the topic more clearly.

Do not contradict the document context.

If the context does not contain enough information,
use your general knowledge when it is appropriate.

Do not mention that you are using a RAG system.
"""

    else:

        document_instruction = """
The question is not sufficiently related to the provided documents.

Answer using your general knowledge.

Do not force the document context into the answer.
"""

    # --------------------------------------------------------
    # CONVERSATION HISTORY
    # --------------------------------------------------------

    history_text = ""

    if history:

        for message in history[-6:]:

            role = message.get(
                "role",
                ""
            )

            content = message.get(
                "content",
                ""
            )

            if role == "user":

                history_text += (
                    f"User: {content}\n"
                )

            elif role == "assistant":

                history_text += (
                    f"Assistant: {content}\n"
                )

    # --------------------------------------------------------
    # DOCUMENT CONTEXT
    # --------------------------------------------------------

    context_text = ""

    if is_rag and context:

        context_text = f"""
DOCUMENT CONTEXT:
{context}
"""

    # --------------------------------------------------------
    # FINAL PROMPT
    # --------------------------------------------------------

    prompt = f"""
<|system|>
{system_prompt}

{document_instruction}
<|user|>

Conversation history:
{history_text}

{context_text}

Current question:
{question}

Write one clear and concise answer.
<|assistant|>
"""

    return prompt


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_for_comparison(text):
    """
    Normalize text for repetition detection.
    """

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        "",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# ============================================================
# REPETITION DETECTION
# ============================================================

def contains_repetition(text):
    """
    Detect obvious repeated sentences or phrases.
    """

    normalized = normalize_for_comparison(
        text
    )

    if not normalized:
        return False

    # --------------------------------------------------------
    # REPEATED SENTENCES
    # --------------------------------------------------------

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text.strip()
    )

    normalized_sentences = []

    for sentence in sentences:

        sentence_normalized = (
            normalize_for_comparison(
                sentence
            )
        )

        if len(sentence_normalized.split()) >= 5:

            normalized_sentences.append(
                sentence_normalized
            )

    sentence_counts = {}

    for sentence in normalized_sentences:

        sentence_counts[sentence] = (
            sentence_counts.get(
                sentence,
                0
            ) + 1
        )

        if (
            sentence_counts[sentence]
            > MAX_SENTENCE_REPEAT
        ):
            return True

    # --------------------------------------------------------
    # REPEATED PHRASES
    # --------------------------------------------------------

    words = normalized.split()

    if len(words) < MIN_REPEAT_WORDS * 3:
        return False

    phrase_counts = {}

    for i in range(
        len(words) - MIN_REPEAT_WORDS + 1
    ):

        phrase = tuple(
            words[
                i:i + MIN_REPEAT_WORDS
            ]
        )

        phrase_counts[phrase] = (
            phrase_counts.get(
                phrase,
                0
            ) + 1
        )

        if phrase_counts[phrase] >= 3:

            return True

    return False


# ============================================================
# CLEAN ANSWER
# ============================================================

def clean_answer(answer):
    """
    Clean generated output.

    Rules:

    - Remove special tokens.
    - Remove accidental SVG/XML starts.
    - Maximum 80 words.
    - After 50 words, stop at the next complete sentence.
    - Avoid repetition.
    - Never intentionally cut a sentence when a complete
      sentence can fit within the limit.
    """

    if not answer:
        return ""

    # --------------------------------------------------------
    # REMOVE SPECIAL TOKENS
    # --------------------------------------------------------

    answer = re.sub(
        r"<\|.*?\|>",
        "",
        answer
    )

    answer = re.sub(
        r"\[/?INST\]",
        "",
        answer,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # REMOVE ACCIDENTAL SVG / MARKUP
    # --------------------------------------------------------

    answer = re.sub(
        r"^\s*svg\s*[\r\n]+",
        "",
        answer,
        flags=re.IGNORECASE
    )

    answer = re.sub(
        r"^\s*(answer|response)\s*:\s*",
        "",
        answer,
        flags=re.IGNORECASE
    )

    # --------------------------------------------------------
    # NORMALIZE WHITESPACE
    # --------------------------------------------------------

    answer = re.sub(
        r"\s+",
        " ",
        answer
    ).strip()

    if not answer:
        return ""

    # --------------------------------------------------------
    # SPLIT INTO SENTENCES
    # --------------------------------------------------------

    sentences = re.split(
        r"(?<=[.!?])\s+",
        answer
    )

    cleaned_sentences = []

    total_words = 0

    reached_sentence_check = False

    # --------------------------------------------------------
    # ADD COMPLETE SENTENCES
    # --------------------------------------------------------

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        sentence_words = sentence.split()

        sentence_count = len(
            sentence_words
        )

        # ----------------------------------------------------
        # REPETITION CHECK
        # ----------------------------------------------------

        candidate = " ".join(
            cleaned_sentences + [sentence]
        )

        if contains_repetition(
            candidate
        ):

            break

        # ----------------------------------------------------
        # MAXIMUM WORD LIMIT
        # ----------------------------------------------------

        if (
            total_words + sentence_count
            <= MAX_ANSWER_WORDS
        ):

            cleaned_sentences.append(
                sentence
            )

            total_words += sentence_count

            # Once 50+ words are reached,
            # we have a complete sentence,
            # so stop.
            if (
                total_words
                >= START_SENTENCE_CHECK_WORDS
            ):

                reached_sentence_check = True
                break

        else:

            # This sentence would exceed
            # the absolute 80-word limit.
            break

    # --------------------------------------------------------
    # BUILD RESULT
    # --------------------------------------------------------

    result = " ".join(
        cleaned_sentences
    ).strip()

    # --------------------------------------------------------
    # IF WE HAVE A GOOD COMPLETE ANSWER
    # --------------------------------------------------------

    if result:

        result_words = result.split()

        if len(result_words) <= MAX_ANSWER_WORDS:
            return result

        return " ".join(
            result_words[
                :MAX_ANSWER_WORDS
            ]
        )

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    words = answer.split()

    if len(words) <= MAX_ANSWER_WORDS:
        return answer

    return " ".join(
        words[
            :MAX_ANSWER_WORDS
        ]
    )


# ============================================================
# GENERATE ANSWER
# ============================================================

def generate_answer(prompt):
    """
    Generate an answer using TinyLlama.
    """

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=2048
    )

    input_ids = inputs["input_ids"]
    attention_mask = inputs[
        "attention_mask"
    ]

    # --------------------------------------------------------
    # GENERATION
    # --------------------------------------------------------

    with torch.no_grad():

        output_ids = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,

            max_new_tokens=MAX_NEW_TOKENS,

            do_sample=False,

            repetition_penalty=1.08,

            no_repeat_ngram_size=4,

            eos_token_id=tokenizer.eos_token_id,

            pad_token_id=(
                tokenizer.pad_token_id
                if tokenizer.pad_token_id
                is not None
                else tokenizer.eos_token_id
            )
        )

    # --------------------------------------------------------
    # REMOVE INPUT TOKENS
    # --------------------------------------------------------

    generated_ids = output_ids[
        0
    ][
        input_ids.shape[1]:
    ]

    answer = tokenizer.decode(
        generated_ids,
        skip_special_tokens=True
    )

    # --------------------------------------------------------
    # CLEAN
    # --------------------------------------------------------

    answer = clean_answer(
        answer
    )

    return answer


# ============================================================
# ASK RAG
# ============================================================

def ask_rag(
    question,
    history=None
):
    """
    Main RAG function.
    """

    if history is None:
        history = []

    question = question.strip()

    if not question:
        return {
            "answer": "",
            "sources": [],
            "score": 0.0,
            "is_rag": False
        }

    # --------------------------------------------------------
    # SIMPLE MESSAGE
    # --------------------------------------------------------

    simple_response = handle_simple_message(
        question
    )

    if simple_response:

        return {
            "answer": simple_response,
            "sources": [],
            "score": 1.0,
            "is_rag": False
        }

    # --------------------------------------------------------
    # RETRIEVE DOCUMENT CONTEXT
    # --------------------------------------------------------

    context, sources, score, is_rag = (
        retrieve_context(question)
    )

    # --------------------------------------------------------
    # CREATE PROMPT
    # --------------------------------------------------------

    prompt = construct_full_prompt(
        question=question,
        context=context,
        history=history,
        is_rag=is_rag
    )

    # --------------------------------------------------------
    # GENERATE
    # --------------------------------------------------------

    answer = generate_answer(
        prompt
    )

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    if not answer:

        answer = (
            "I could not generate a clear answer."
        )

    return {
        "answer": answer,
        "sources": sources if is_rag else [],
        "score": score,
        "is_rag": is_rag
    }


# ============================================================
# STREAMING GENERATION
# ============================================================

def ask_rag_stream(
    question,
    history=None
):
    """
    Streaming-compatible RAG function.

    The model generation happens in a background thread,
    but the final answer is cleaned before it is returned.
    This guarantees the 80-word and repetition rules.
    """

    if history is None:
        history = []

    question = question.strip()

    if not question:
        yield {
            "type": "token",
            "content": ""
        }

        return

    # --------------------------------------------------------
    # SIMPLE MESSAGE
    # --------------------------------------------------------

    simple_response = handle_simple_message(
        question
    )

    if simple_response:

        yield {
            "type": "token",
            "content": simple_response
        }

        return

    # --------------------------------------------------------
    # RETRIEVE
    # --------------------------------------------------------

    context, sources, score, is_rag = (
        retrieve_context(question)
    )

    # --------------------------------------------------------
    # SEND SOURCES FIRST
    # --------------------------------------------------------

    if is_rag:

        yield {
            "type": "sources",
            "sources": sources,
            "score": score
        }

    # --------------------------------------------------------
    # BUILD PROMPT
    # --------------------------------------------------------

    prompt = construct_full_prompt(
        question=question,
        context=context,
        history=history,
        is_rag=is_rag
    )

    # --------------------------------------------------------
    # TOKENIZER
    # --------------------------------------------------------

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=2048
    )

    # --------------------------------------------------------
    # STREAMER
    # --------------------------------------------------------

    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True
    )

    generation_kwargs = {
        "input_ids": inputs["input_ids"],
        "attention_mask": inputs["attention_mask"],

        "streamer": streamer,

        "max_new_tokens": MAX_NEW_TOKENS,

        "do_sample": False,

        "repetition_penalty": 1.08,

        "no_repeat_ngram_size": 4,

        "eos_token_id": tokenizer.eos_token_id,

        "pad_token_id": (
            tokenizer.pad_token_id
            if tokenizer.pad_token_id
            is not None
            else tokenizer.eos_token_id
        )
    }

    # --------------------------------------------------------
    # BACKGROUND GENERATION
    # --------------------------------------------------------

    generated_text = []

    def generate():

        with torch.no_grad():

            model.generate(
                **generation_kwargs
            )

    thread = Thread(
        target=generate
    )

    thread.start()

    # --------------------------------------------------------
    # COLLECT GENERATED TEXT
    # --------------------------------------------------------

    for new_text in streamer:

        generated_text.append(
            new_text
        )

    thread.join()

    # --------------------------------------------------------
    # CLEAN FINAL ANSWER
    # --------------------------------------------------------

    full_answer = "".join(
        generated_text
    )

    full_answer = clean_answer(
        full_answer
    )

    # --------------------------------------------------------
    # RETURN FINAL ANSWER
    # --------------------------------------------------------

    yield {
        "type": "token",
        "content": full_answer
    }


# ============================================================
# OPTIONAL TEST
# ============================================================

if __name__ == "__main__":

    print("\nRAG system ready.")

    print(
        f"Documents loaded: {len(chunks)}"
    )

    while True:

        try:

            question = input(
                "\nYou: "
            ).strip()

        except KeyboardInterrupt:

            print("\nGoodbye.")

            break

        if not question:
            continue

        if question.lower() in {
            "exit",
            "quit"
        }:

            print("Goodbye.")

            break

        result = ask_rag(
            question
        )

        print(
            "\nAssistant:",
            result["answer"]
        )

        if result["sources"]:

            print(
                "\nSources:"
            )

            for source in result["sources"]:

                page = source.get(
                    "page"
                )

                if page:

                    print(
                        f"- {source['source']} "
                        f"(page {page})"
                    )

                else:

                    print(
                        f"- {source['source']}"
                    )