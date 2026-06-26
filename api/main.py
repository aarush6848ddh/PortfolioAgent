from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.db import get_db

app = FastAPI()

app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/portfolio")
def get_portfolio():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT ticker, shares, cost_basis FROM holdings WHERE sold_at IS NULL")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"ticker": row[0], "shares": row[1], "cost_basis": row[2]} for row in rows]
 

