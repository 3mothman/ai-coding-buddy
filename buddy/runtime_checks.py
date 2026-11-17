"""Offline packaged dependency check; never opens a device or makes an API request."""
def verify_offline_runtime():
    from google.genai import types
    from .gemini_analysis import AnalysisResult
    from .live_voice import live_config
    from .audio_io import PCMResampler
    import sounddevice
    types.LiveConnectConfig.model_validate(live_config())
    types.GenerateContentConfig.model_validate({
        "response_mime_type": "application/json",
        "response_json_schema": AnalysisResult.model_json_schema()})
    resampler = PCMResampler(48000, 16000)
    output = resampler.convert(bytes(4800 * 2), final=True)
    if len(output) != 1600 * 2:
        raise RuntimeError("Packaged audio resampling check failed")
