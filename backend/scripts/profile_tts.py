"""Profile RFC 2328 — focused on section sizes and intro synthesis time."""
import asyncio, sys, time, json
sys.path.insert(0, '.')
from rfc_fetcher import get_rfc_text
from rfc_parser import parse_rfc

async def main():
    raw = await get_rfc_text(2328)
    parsed = parse_rfc(2328, raw)
    sections = parsed["sections"]

    # Dump section sizes as JSON for clean output
    info = []
    for i, s in enumerate(sections):
        info.append({
            "idx": i,
            "type": s["type"],
            "heading": s["heading"][:60],
            "chars": len(s["content"]),
            "words": len(s["content"].split()),
        })
    
    # Sort by chars desc, show top 10
    by_size = sorted(info, key=lambda x: -x["chars"])
    print("=== TOP 10 LARGEST SECTIONS ===")
    for s in by_size[:10]:
        print(f"  [{s['idx']:3d}] {s['chars']:6d} chars  {s['words']:5d} words  {s['heading']}")

    # Find intro
    intro = None
    for s in info:
        if "introduction" in s["heading"].lower() or "1. " in s["heading"]:
            if intro is None or s["chars"] > intro["chars"]:
                intro = s
    
    if intro:
        print(f"\n=== INTRODUCTION ===")
        print(f"Section {intro['idx']}: {intro['chars']} chars, {intro['words']} words")
    
    # Time synthesis for a few sections of different sizes  
    import edge_tts
    test_indices = []
    if intro:
        test_indices.append(intro["idx"])
    # Also test idx 0 (typically small) and the largest
    test_indices.append(0)
    test_indices.append(by_size[0]["idx"])
    # Deduplicate
    test_indices = list(dict.fromkeys(test_indices))
    
    print(f"\n=== SYNTHESIS TIMING ===")
    for idx in test_indices:
        sec = sections[idx]
        text = sec["content"]
        chars = len(text)
        print(f"\nSection {idx} ({sec['heading'][:40]}): {chars} chars")
        
        t0 = time.time()
        comm = edge_tts.Communicate(text, "en-US-GuyNeural", boundary="WordBoundary")
        audio_size = 0
        first_audio = None
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                if first_audio is None:
                    first_audio = time.time() - t0
                audio_size += len(chunk["data"])
        total = time.time() - t0
        print(f"  First audio chunk: {first_audio:.2f}s")
        print(f"  Total synthesis:   {total:.2f}s")
        print(f"  Audio size:        {audio_size:,} bytes")

asyncio.run(main())
