from pathlib import Path

path = Path("KREME/krem/server/__init__.py")
content = path.read_text(encoding="utf-8")

old_import = "from krem.coach import BenchmarkRegistry, compare_lap_to_benchmark, generate_coach_advice"
new_import = "from krem.coach import BenchmarkRegistry, compare_lap_to_benchmark, generate_coach_advice, get_gemini_api_key, persist_gemini_api_key"

old_status = """    @app.get("/api/coach/status")
    async def coach_status():
        \"\"\"Check if Gemini API key is configured.\"\"\"
        has_key = bool(os.environ.get("GEMINI_API_KEY"))
        return {
            "hasApiKey": has_key,
            "model": "gemini-3.5-flash",
        }

    @app.post("/api/coach/key")
    async def set_coach_api_key(req: ApiKeyRequest):
        \"\"\"Configure or update Gemini API key dynamically.\"\"\"
        if not req.apiKey or not req.apiKey.strip():
            raise HTTPException(status_code=400, detail="API key cannot be empty")
        os.environ["GEMINI_API_KEY"] = req.apiKey.strip()
        return {"status": "ok", "message": "Gemini API key configured successfully"}"""

new_status = """    @app.get("/api/coach/status")
    async def coach_status():
        \"\"\"Check if Gemini API key is configured.\"\"\"
        api_key = get_gemini_api_key()
        return {
            "hasApiKey": bool(api_key),
            "model": "gemini-3.5-flash",
        }

    @app.post("/api/coach/key")
    async def set_coach_api_key(req: ApiKeyRequest):
        \"\"\"Configure or update Gemini API key dynamically.\"\"\"
        if not req.apiKey or not req.apiKey.strip():
            raise HTTPException(status_code=400, detail="API key cannot be empty")
        persist_gemini_api_key(req.apiKey.strip())
        return {"status": "ok", "message": "Gemini API key configured successfully"}"""

old_has_key = '"hasApiKey": bool(os.environ.get("GEMINI_API_KEY")),'
new_has_key = '"hasApiKey": bool(get_gemini_api_key()),'

assert old_import in content, "old_import not found"
assert old_status in content, "old_status not found"
assert old_has_key in content, "old_has_key not found"

content = content.replace(old_import, new_import, 1)
content = content.replace(old_status, new_status, 1)
content = content.replace(old_has_key, new_has_key, 1)

path.write_text(content, encoding="utf-8")
print("Updated krem/server/__init__.py successfully!")
