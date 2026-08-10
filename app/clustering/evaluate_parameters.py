import numpy as np
from app.clustering.hdbscan_runner import HDBSCANRunner
from app.processing.embeddings import EmbeddingProvider

def evaluate():
    print("========================================")
    print("STAGE 9 — PARAMETER SWEEP")
    print("========================================")
    
    # Generate some controlled dataset simulating multi-lingual vectors 
    embedder = EmbeddingProvider()
    fixtures = [
        "Vijay announces TVK meeting",
        "Vijay will meet district secretaries",
        "TVK political meeting announced",
        "விஜய் அரசியல் கூட்டத்தை அறிவித்தார்",
        "vijay oda meeting start aachu", # 5 highly related
        
        "Chennai received heavy rainfall",
        "Flood warning in Chennai tomorrow",
        "சென்னையில் கனமழை", # 3 highly related
        
        "India wins cricket match against Australia",
        "T20 World Cup finals result", # 2 highly related
        
        "Happy birthday bro", # 1 noise
        "SALE 50% OFF", # 1 noise
        "🔥🔥🔥" # 1 noise
    ]
    
    print("Loading test embeddings...")
    embeddings = np.array([embedder.embed(text) for text in fixtures])
    signal_ids = list(range(1, len(fixtures) + 1))
    
    matrix = [(2,1), (3,1), (3,2), (4,2), (5,2), (5,3)]
    
    print("\n| min_size | min_samples | clusters | noise | coherence |")
    print("|----------|-------------|----------|-------|-----------|")
    
    for size, samples in matrix:
        runner = HDBSCANRunner(min_cluster_size=size, min_samples=samples)
        result = runner.fit(embeddings, signal_ids)
        
        clusters = result["metrics"]["cluster_count"]
        noise = result["metrics"]["noise_count"]
        noise_pct = int((noise / len(fixtures)) * 100)
        
        # calculate average coherence
        coh_vals = [d["coherence"] for d in result["clusters"].values()]
        avg_coh = sum(coh_vals) / len(coh_vals) if coh_vals else 0.0
        
        print(f"| {size:<8} | {samples:<11} | {clusters:<8} | {noise_pct}% ({noise:<2})| {avg_coh:.3f}     |")

if __name__ == "__main__":
    evaluate()
