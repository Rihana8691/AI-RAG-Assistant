# AI RAG Assistant

A professional-grade Retrieval-Augmented Generation (RAG) assistant with a sleek, ChatGPT-inspired user interface. This project allows users to upload PDF documents and ask questions based on their content, providing accurate, grounded answers with citations.

## 🚀 Features

- **ChatGPT-Style UI:** A clean, responsive dark-themed interface with a collapsible sidebar and auto-expanding input field.
- **RAG Engine:** Powered by `TinyLlama-1.1B-Chat` for text generation and `all-MiniLM-L6-v2` for high-quality document embeddings.
- **Dynamic Knowledge Base:** 
  - Upload multiple PDFs simultaneously.
  - View a list of indexed documents in the sidebar.
  - Open and view uploaded PDFs directly from the browser.
  - Delete documents and automatically re-index the memory.
- **Persistent Memory:** Uses FAISS for efficient similarity search, with local storage for indexes to ensure fast startup times.
- **Smart Citations:** Collapsible sections in AI responses showing exact text snippets and page numbers from the source documents.
- **Conversation History:** Previous chats are saved in `localStorage`, allowing users to resume conversations later.
- **Streaming Responses:** Real-time, token-by-token answer generation for a modern AI experience.

## 🛠️ Tech Stack

- **Frontend:** HTML5, CSS3 (Tailwind CSS), JavaScript (Vanilla).
- **Backend:** Python, FastAPI, Uvicorn.
- **AI Libraries:** Transformers (Hugging Face), PyTorch, Sentence-Transformers.
- **Vector Database:** FAISS (Facebook AI Similarity Search).
- **Document Processing:** PyPDF.

## 📦 Installation & Setup

### 1. Prerequisites
- Python 3.8 or higher.
- A modern web browser.

### 2. Clone the Repository
```bash
git clone https://github.com/Rihana8691/AI-RAG-Assistant.git
cd AI-RAG-Assistant
```

### 3. Setup Virtual Environment (Recommended)
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the Backend
```bash
python -m uvicorn backend.main:app --reload
```
*Note: The first startup may take a few minutes to download the AI models (~2.5GB).*

### 6. Open the Frontend
Open `frontend/index.html` in your web browser.

## 📖 How to Use

1. **Upload PDFs:** Click the "Upload PDFs" button in the sidebar or message bar. Drag and drop your files and wait for the "Successfully Indexed" message.
2. **Ask Questions:** Type a question about your documents in the message bar and press Enter.
3. **View Sources:** Click on "View Citations" under the AI's response to see which document sections were used.
4. **Manage History:** Use the sidebar to start a new chat or switch between previous conversations.

## 🛡️ Security

- Integrated **DOMPurify** to prevent XSS attacks from generated content.
- Robust input sanitization and error handling.
- Localized AI execution (TinyLlama) for data privacy.

---
Built as part of an AI Sector Project.
