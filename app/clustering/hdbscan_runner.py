import hdbscan
import numpy as np
from typing import List, Dict, Tuple
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
from sklearn.metrics import silhouette_score

class HDBSCANRunner:
    """Deterministic executor for HDBSCAN clustering over native PyTorch arrays"""
    
    def __init__(self, min_cluster_size: int = 3, min_samples: int = 2):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.version = getattr(hdbscan, '__version__', 'unknown')
        
    def _calculate_coherence(self, feature_matrix: np.ndarray) -> float:
        """Determines the semantic coherence of a cluster (average pairwise cosine similarity)"""
        if len(feature_matrix) <= 1:
            return 1.0
        
        sim_matrix = cosine_similarity(feature_matrix)
        # Extract upper triangle (excluding diagonal) to get unique pairwise distances
        mask = np.triu(np.ones_like(sim_matrix, dtype=bool), k=1)
        pairwise_sims = sim_matrix[mask]
        
        if len(pairwise_sims) == 0:
            return 1.0
            
        return float(np.mean(pairwise_sims))
        
    def _find_representatives(self, feature_matrix: np.ndarray, member_ids: List[int], max_candidates: int = 3) -> List[int]:
        """Finds representative clusters based on Medoid bounding (closest to cluster centroid)"""
        if not member_ids:
            return []
            
        if len(member_ids) <= max_candidates:
            return member_ids
            
        # Calculate Medoid (closest to geographic center of members)
        centroid = np.mean(feature_matrix, axis=0).reshape(1, -1)
        # Cosine distance naturally maps to Euclidean for L2-normalized representations
        sims = cosine_similarity(feature_matrix, centroid).flatten()
        
        # Sort by highest similarity to centroid
        best_indices = np.argsort(sims)[::-1][:max_candidates]
        return [member_ids[i] for i in best_indices]

    def fit(self, embeddings: np.ndarray, signal_ids: List[int]) -> Dict:
        """Executes Clustering generating full membership payloads securely"""
        if len(embeddings) == 0:
            return {"clusters": {}, "noise_ids": [], "metrics": {}}
            
        if len(embeddings) < self.min_cluster_size:
            # Cannot form any clusters natively natively
            return {"clusters": {}, "noise_ids": signal_ids, "metrics": {}}
            
        # Initialize HDBSCAN leveraging Euclidean (mapping perfectly to Cosine for L2 vectors)
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            metric='euclidean',
            cluster_selection_epsilon=0.0
        )
        
        cluster_labels = clusterer.fit_predict(embeddings)
        probabilities = clusterer.probabilities_
        outlier_scores = getattr(clusterer, 'outlier_scores_', np.zeros(len(embeddings)))
        
        # Group by label
        clusters_map = {}
        noise_ids = []
        
        for idx, label in enumerate(cluster_labels):
            sig_id = signal_ids[idx]
            if label == -1:
                noise_ids.append(sig_id)
            else:
                if label not in clusters_map:
                    clusters_map[label] = {
                        "member_ids": [],
                        "member_indices": [], # For matrix subsetting
                        "probabilities": [],
                        "outlier_scores": []
                    }
                clusters_map[label]["member_ids"].append(sig_id)
                clusters_map[label]["member_indices"].append(idx)
                clusters_map[label]["probabilities"].append(probabilities[idx])
                clusters_map[label]["outlier_scores"].append(outlier_scores[idx])

        # Calculate Coherence and Representatives
        final_clusters = {}
        for label, data in clusters_map.items():
            cluster_embeddings = embeddings[data["member_indices"]]
            coherence = self._calculate_coherence(cluster_embeddings)
            representatives = self._find_representatives(cluster_embeddings, data["member_ids"])
            
            final_clusters[f"CLUSTER_{label}"] = {
                "size": len(data["member_ids"]),
                "coherence": coherence,
                "representatives": representatives,
                "members": [
                    {
                        "signal_id": data["member_ids"][i],
                        "probability": float(data["probabilities"][i]),
                        "outlier_score": float(data["outlier_scores"][i] if data["outlier_scores"] is not None else 0.0)
                    } for i in range(len(data["member_ids"]))
                ]
            }
            
        # Calculate Silhouette Score safely
        sil_score = "NOT_APPLICABLE"
        n_clusters = len(final_clusters)
        if n_clusters > 1 or (n_clusters == 1 and len(noise_ids) > 0):
            try:
                # Discard noise (-1) for internal coherence metric tests unless bounding explicit comparisons natively
                valid_mask = cluster_labels != -1
                if np.sum(valid_mask) > self.min_cluster_size:
                    val_emb = embeddings[valid_mask]
                    val_lab = cluster_labels[valid_mask]
                    if len(np.unique(val_lab)) > 1:
                        # Map cosine structurally natively
                        dist_matrix = 1.0 - cosine_similarity(val_emb)
                        sil_score = float(silhouette_score(dist_matrix, val_lab, metric="precomputed"))
            except Exception:
                pass

        return {
            "clusters": final_clusters,
            "noise_ids": noise_ids,
            "metrics": {
                "total_signals": len(signal_ids),
                "noise_count": len(noise_ids),
                "cluster_count": n_clusters,
                "silhouette_score": sil_score
            }
        }
