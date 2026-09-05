from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from backend.rag import ask_rag, process_pdfs, ask_rag_stream

import os
import shutil
import json


app = FastAPI()


# =========================
# Static Files (Documents)
# =========================

# This allows the frontend to open uploaded PDFs directly
app.mount("/view-documents", StaticFiles(directory="documents"), name="view-documents")


# =========================
# CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Documents folder
# =========================

UPLOAD_FOLDER = "documents"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================
# Models
# =========================

class Message(BaseModel):
    role: str
    content: str

class Question(BaseModel):
    question: str
    history: Optional[List[Message]] = []


# =========================
# Home
# =========================

@app.get("/")
def home():

    return {
        "message": "RAG Backend is running!"
    }


# =========================
# Upload multiple PDFs
# =========================

@app.post("/upload")
async def upload_pdfs(
    files: list[UploadFile] = File(...)
):

    uploaded_files = []

    # Save each PDF
    for file in files:

        if not file.filename.lower().endswith(".pdf"):

            continue


        file_path = os.path.join(
            UPLOAD_FOLDER,
            file.filename
        )


        with open(
            file_path,
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                file.file,
                buffer
            )


        uploaded_files.append(
            file.filename
        )


    if len(uploaded_files) == 0:

        return {
            "success": False,
            "message": "No PDF files were uploaded."
        }


    # =========================
    # Process ONLY NEW PDFs
    # =========================

    new_pdf_paths = [
        os.path.join(UPLOAD_FOLDER, fname)
        for fname in uploaded_files
    ]

    number_of_chunks = process_pdfs(
        new_pdf_paths,
        is_append=True
    )


    return {

        "success": True,

        "files": uploaded_files,

        "total_documents": len([f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(".pdf")]),

        "message": (
            "PDF files uploaded and "
            "processed successfully!"
        ),

        "chunks": number_of_chunks

    }


# =========================
# List Documents
# =========================

@app.get("/documents")
async def list_documents():
    import backend.rag as rag

    # Extract unique filenames from the actual live sources in memory
    unique_files = []
    for s in rag.chunk_sources:
        # s is a dict: {"source": "filename.pdf", "page": 1}
        if isinstance(s, dict):
            fname = s.get("source")
        else:
            # Fallback for old string-based sources if any
            fname = str(s).split(" (Page")[0]

        if fname and fname not in unique_files:
            unique_files.append(fname)

    return {"documents": unique_files}


# =========================
# Delete Document
# =========================

@app.delete("/documents/{filename}")
async def delete_document(filename: str):
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    if os.path.exists(file_path):
        os.remove(file_path)

        # We must re-process the remaining PDFs to update the AI's memory
        pdf_paths = [os.path.join(UPLOAD_FOLDER, f) for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(".pdf")]
        process_pdfs(pdf_paths)

        return {"success": True, "message": f"Deleted {filename} and updated index."}

    return {"success": False, "message": "File not found."}


# =========================
# Ask question
# =========================

@app.post("/ask")
def ask_question(
    data: Question
):
    history_list = [{"role": m.role, "content": m.content} for m in data.history] if data.history else []

    result = ask_rag(
        data.question,
        history=history_list
    )


    return {

        "question": data.question,

        "answer": result["answer"],

        "sources": result["sources"]

    }


# =========================
# Ask question (streaming)
# =========================

@app.post("/ask-stream")
async def ask_question_stream(
    data: Question
):
    history_list = [{"role": m.role, "content": m.content} for m in data.history] if data.history else []

    async def generate():
        try:
            # Stream the answer
            for chunk in ask_rag_stream(data.question, history=history_list):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )