#!/usr/bin/env python3
"""
Helper script to insert AgentOptima tracker into Aris orchestrator
Run this after AgentOptima API is live
"""

import sys
import re

ORCHESTRATOR_PATH = "/root/.aris/orchestrator.py"

INJECTION_CODE = '''
# ===== AGENTOPTIMA TRACKER =====
import sys
sys.path.insert(0, '/root/.openclaw/workspace/AgentOptima')
from integration.aris_agent import ArisTracker

# Initialize tracker with your default model
tracker = ArisTracker(model_name="claude-sonnet-4-6")

'''

def insert_tracker(aris_file):
    """Insert tracker initialization at the top of the file"""
    try:
        with open(aris_file, 'r') as f:
            content = f.read()
        
        # Find the first imports section or top of file
        lines = content.split('\n')
        
        # Insert after the first few lines (shebang if present, imports)
        insert_index = 0
        for i, line in enumerate(lines):
            if line.startswith('#') or line.strip() == '' or line.startswith('import ') or line.startswith('from '):
                insert_index = i + 1
            else:
                break
        
        # Inject the code
        lines.insert(insert_index, INJECTION_CODE.strip() + '\n')
        
        # Write back
        with open(aris_file, 'w') as f:
            f.write('\n'.join(lines))
        
        print(f"✅ Tracker injected into {aris_file}")
        print(f"📍 Inserted at line {insert_index + 1}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error injecting tracker: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        aris_file = sys.argv[1]
    else:
        aris_file = ORCHESTRATOR_PATH
    
    print(f"🔧 Preparing AgentOptima tracker injection...")
    print(f"📄 Target: {aris_file}")
    print("-" * 50)
    
    insert_tracker(aris_file)
    print("-" * 50)
    print("✅ Ready! Next step:")
    print("   Call tracker.after_task(context, success=True/False, notes=...)")
    print("   after each task completion in your orchestrator")
