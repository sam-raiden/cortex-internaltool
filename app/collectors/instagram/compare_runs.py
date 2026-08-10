import os
import json
import pathlib
import glob

def compare():
    out_dir = pathlib.Path("output/repeatability")
    if not out_dir.exists():
        print("No telemetry data found in output/repeatability/")
        return
        
    run_files = sorted(list(out_dir.glob("run_*.json")))
    if not run_files:
        print("No run files to compare.")
        return
        
    print("========================================")
    print("INSTAGRAM REPEATABILITY COMPARISON")
    print("========================================")

    runs = []
    
    for fpath in run_files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
            runs.append(data)
            
            run_name = fpath.name.split('.')[0].upper().replace('_', ' ')
            
            print(f"\n{run_name}:")
            print(f"Profiles      : {data.get('pages_attempted')} attempted, {data.get('pages_accessible')} successful, {data.get('pages_failed')} failed")
            print(f"Posts         : {data.get('posts_discovered')} discovered, {data.get('unique_posts')} unique")
            print(f"New           : {data.get('new_posts')}")
            print(f"Existing      : {data.get('existing_posts')}")
            print(f"Errors        : {data.get('parser_errors')} parser, {data.get('navigation_errors')} nav, {data.get('timeouts')} timeouts")
            
            acc_events = data.get('login_wall_events', 0) + data.get('challenge_events', 0) + data.get('access_denied_events', 0)
            print(f"Access events : {acc_events}")
            print(f"Runtime       : {data.get('duration_ms')} ms")
            
    # Calculate across all runs
    total_runs = len(runs)
    total_profiles = sum(r.get("pages_attempted", 0) for r in runs)
    total_success = sum(r.get("pages_accessible", 0) for r in runs)
    
    total_discovered = sum(r.get("posts_discovered", 0) for r in runs)
    total_new = sum(r.get("new_posts", 0) for r in runs)
    
    total_failures = sum(r.get("pages_failed", 0) for r in runs)
    
    total_events = sum(
        r.get('login_wall_events', 0) + r.get('challenge_events', 0) + r.get('access_denied_events', 0)
        for r in runs
    )
    
    avg_runtime = sum(r.get("duration_ms", 0) for r in runs) / max(1, total_profiles)
    
    success_rate = (total_success / max(1, total_profiles)) * 100
    discovery_rate = total_discovered / max(1, total_success)
    new_post_rate = (total_new / max(1, total_discovered)) * 100
    failure_rate = (total_failures / max(1, total_profiles)) * 100

    print("\n----------------------------------------")
    print("AGGREGATE METRICS")
    print("----------------------------------------")
    print(f"Total runs                  : {total_runs}")
    print(f"Profile success rate        : {success_rate:.1f}%")
    print(f"Post discovery rate (avg)   : {discovery_rate:.1f} per successful profile")
    print(f"New-post rate               : {new_post_rate:.1f}%")
    print(f"Failure rate                : {failure_rate:.1f}%")
    print(f"Challenge/access-event count: {total_events}")
    print(f"Average page runtime        : {avg_runtime:.0f} ms")
    
    print("\n========================================")

if __name__ == "__main__":
    compare()
