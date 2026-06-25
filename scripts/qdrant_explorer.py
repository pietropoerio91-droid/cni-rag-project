import streamlit as st
st.set_page_config(page_title="Qdrant Explorer", layout="wide")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.vectorstore.qdrant_client import QdrantClientManager

st.title("Qdrant Explorer")
st.caption("Documenti indicizzati nel database vettoriale")

@st.cache_resource
def get_manager():
    return QdrantClientManager()

manager = get_manager()
client = manager.get_client()
collection_name = manager.collection_name

col_info = client.get_collection(collection_name)
total = col_info.points_count
st.metric("Totale punti indicizzati", total)

st.divider()

mode = st.radio("Modalità esplorazione", ["Sfoglia", "Cerca"], horizontal=True)

if mode == "Sfoglia":
    limit = st.slider("Documenti per pagina", 10, 100, 20)
    offset = st.number_input("Offset", 0, max(0, total - 1), 0, step=limit)

    if st.button("Carica"):
        points = client.scroll(collection_name, limit=limit, offset=offset)[0]
        for pt in points:
            with st.expander(f"{pt.payload.get('title', 'Senza titolo')}  (score: {pt.score:.3f})"):
                st.markdown(f"**Fonte:** {pt.payload.get('source', 'N/A')}")
                st.markdown(f"**Categoria:** {pt.payload.get('category', 'N/A')}")
                st.markdown(f"**Chunk:** {pt.payload.get('chunk_index', 0)}/{pt.payload.get('total_chunks', 0)}")
                st.text_area("Contenuto", pt.payload.get("content", ""), height=200)

elif mode == "Cerca":
    query = st.text_input("Testo da cercare")
    top_k = st.slider("Risultati", 5, 50, 10)
    if query:
        from src.core.model_factory import create_embeddings
        embedder = create_embeddings()
        vector = embedder.embed_query(query)
        results = client.query_points(collection_name=collection_name, query=vector, limit=top_k)

        st.subheader(f"{len(results.points)} risultati")
        for pt in results.points:
            with st.expander(f"{pt.payload.get('title', 'Senza titolo')}  (score: {pt.score:.3f})"):
                st.markdown(f"**Fonte:** {pt.payload.get('source', 'N/A')}")
                st.markdown(f"**Categoria:** {pt.payload.get('category', 'N/A')}")
                st.text_area("Contenuto", pt.payload.get("content", ""), height=200)
