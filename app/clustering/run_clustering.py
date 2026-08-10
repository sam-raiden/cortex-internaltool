import hdbscan
import time
import argparse
import numpy as np
from app.clustering.hdbscan_runner import HDBSCANRunner
from app.storage.database import SessionLocal
from app.models.schema import ProcessedSignal, ClusterRun, Cluster, ClusterMember

class ClusteringService:
    def __init__(self, min_cluster_size=2, min_samples=1):
        self.runner = HDBSCANRunner(min_cluster_size=min_cluster_size, min_samples=min_samples)
        self.db = SessionLocal()
        
    def run(self, limit=100, diagnostic=False):
        print("========================================")
        print("STAGE 9 — HDBSCAN CLUSTERING")
        print("========================================\n")
        
        # Load from DB
        query = self.db.query(ProcessedSignal).filter(ProcessedSignal.embedding != None, ProcessedSignal.signal_quality != 'INSUFFICIENT')
        if limit > 0:
            query = query.limit(limit)
            
        signals = query.all()
        
        embeddings = []
        signal_ids = []
        valid = 0
        skipped = 0
        
        for s in signals:
            try:
                emb_array = np.array(s.embedding, dtype=np.float32)
                if len(emb_array) == 384:
                    embeddings.append(emb_array)
                    signal_ids.append(s.id)
                    valid += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
                
        print("DATASET")
        print(f"Embeddings evaluated: {len(signals)}")
        print(f"Valid embeddings: {valid}")
        print(f"Skipped invalid: {skipped}\n")
        
        print("CLUSTERING")
        print(f"Model: HDBSCAN")
        print(f"min_cluster_size: {self.runner.min_cluster_size}")
        print(f"min_samples: {self.runner.min_samples}\n")
        
        # Avoid crashing on 0
        if valid < self.runner.min_cluster_size:
            print("Status: NOT_ENOUGH_DATA")
            return
            
        result = self.runner.fit(np.array(embeddings), signal_ids)
        metrics = result["metrics"]
        clusters = result["clusters"]
        
        print(f"Clusters: {metrics['cluster_count']}")
        print(f"Clustered signals: {metrics['total_signals'] - metrics['noise_count']}")
        print(f"Noise signals: {metrics['noise_count']}")
        if metrics['total_signals'] > 0:
            print(f"Noise percentage: {int((metrics['noise_count'] / metrics['total_signals']) * 100)}%\n")
        
        # Size distribution
        sizes = {1:0, 2:0, 3:0, '4+':0}
        avg_coh = []
        
        for c in clusters.values():
            s = c["size"]
            if s == 1: sizes[1] += 1
            elif s == 2: sizes[2] += 1
            elif s == 3: sizes[3] += 1
            else: sizes['4+'] += 1
            avg_coh.append(c["coherence"])
            
        print("CLUSTER SIZE")
        for k, v in sizes.items():
            print(f"{k} signal(s): {v}")
            
        val_coh = sum(avg_coh) / len(avg_coh) if avg_coh else 0.0
        med_coh = float(np.median(avg_coh)) if avg_coh else 0.0
        
        print(f"\nQUALITY")
        print(f"Average coherence: {val_coh:.3f}")
        print(f"Median coherence: {med_coh:.3f}")
        print(f"Silhouette: {metrics['silhouette_score']}\n")
        
        if not diagnostic:
            run_name = f"r_{int(time.time())}"
            # Database persistence 
            run = ClusterRun(
                run_name=run_name,
                embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
                hdbscan_version=hdbscan.__version__,
                min_cluster_size=self.runner.min_cluster_size,
                min_samples=self.runner.min_samples
            )
            self.db.add(run)
            self.db.commit()
            
            for cid_label, cdata in clusters.items():
                cluster = Cluster(
                    run_id=run.id,
                    cluster_label=cid_label,
                    signal_count=cdata["size"],
                    coherence_score=cdata["coherence"]
                )
                self.db.add(cluster)
                self.db.commit()
                
                # Members
                for mem in cdata["members"]:
                    cm = ClusterMember(
                        cluster_id=cluster.id,
                        signal_id=mem["signal_id"],
                        similarity_score=cdata["coherence"], # placeholder
                        membership_probability=mem["probability"],
                        outlier_score=mem["outlier_score"],
                        is_representative=mem["signal_id"] in cdata["representatives"]
                    )
                    self.db.add(cm)
                self.db.commit()
            print(f"[DB] Persisted under Run ID: {run.id}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--min-cluster-size', type=int, default=2)
    parser.add_argument('--min-samples', type=int, default=1)
    args = parser.parse_args()
    
    svc = ClusteringService(min_cluster_size=args.min_cluster_size, min_samples=args.min_samples)
    svc.run(limit=args.limit, diagnostic=args.diagnostic)
