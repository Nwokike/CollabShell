import asyncio
import os
import sys

# Add src/ to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from services.colab_service import ColabService
from colab_cli.auth import TOKEN_CONFIG_PATH

async def test():
    service = ColabService()
    
    # 1. Clear previous saved verifier or tokens to start fresh
    verifier_path = os.path.join(os.path.dirname(TOKEN_CONFIG_PATH), "code_verifier.txt")
    if os.path.exists(verifier_path):
        os.remove(verifier_path)
        
    print("[*] Generating Auth URL...")
    url = await service.get_auth_url()
    print(f"[*] URL: {url}")
    
    # Check if verifier file exists and is populated
    if os.path.exists(verifier_path):
        with open(verifier_path, "r") as f:
            verifier = f.read().strip()
        print(f"[+] Code verifier saved successfully: {verifier[:10]}... ({len(verifier)} chars)")
    else:
        print("[-] Error: Code verifier file NOT created!")
        sys.exit(1)
        
    print("[+] Test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test())
