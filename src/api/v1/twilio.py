import os
import time
import json
import hmac
import hashlib
import base64
import requests
from flask import jsonify, request, current_app, Response

from src.api.v1 import v1


_INTAKE_TOKEN = os.getenv("INTAKE_TOKEN")
_INTAKE_URL = os.getenv("INTAKE_URL")
_TWILIO_RECORDING_CALLBACK = os.getenv("TWILIO_RECORDING_CALLBACK")
_TWILIO_TRANSCRIPTION_CALLBACK = os.getenv("TWILIO_TRANSCRIPTION_CALLBACK")
_TWILIO_VOICE_PROMPT = os.getenv("TWILIO_VOICE_PROMPT") or "Thanks. Please describe your issue after the beep."
_TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")


def _post_to_intake(payload):
    if not _INTAKE_TOKEN:
        return None, (jsonify({"error": "config_error", "message": "INTAKE_TOKEN not configured"}), 500)

    body_str = json.dumps(payload, separators=(",", ":"))
    ts_val = str(int(time.time()))
    signature = hmac.new(
        _INTAKE_TOKEN.encode("utf-8"),
        msg=f"{ts_val}.{body_str}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    target_url = _INTAKE_URL or request.url_root.rstrip("/") + "/api/v1/intake"
    headers = {
        "Content-Type": "application/json",
        "X-Intake-Token": _INTAKE_TOKEN,
        "X-Timestamp": ts_val,
        "X-Signature": signature,
    }

    try:
        resp = requests.post(target_url, headers=headers, data=body_str, timeout=5)
        return resp, None
    except requests.RequestException as exc:
        return None, (jsonify({"error": "forward_failed", "message": str(exc)}), 502)


def _verify_twilio_signature():
    if not _TWILIO_AUTH_TOKEN:
        current_app.logger.warning("TWILIO_AUTH_TOKEN not configured; skipping signature verification.")
        return True, None

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        return False, (jsonify({"error": "unauthorized", "message": "missing_twilio_signature"}), 401)

    url = request.url
    params = request.form.to_dict(flat=True) if request.form else {}
    base = url + "".join(f"{key}{params[key]}" for key in sorted(params))
    digest = hmac.new(_TWILIO_AUTH_TOKEN.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")

    if not hmac.compare_digest(expected, signature):
        return False, (jsonify({"error": "unauthorized", "message": "invalid_twilio_signature"}), 401)
    return True, None


@v1.route("/twilio/recording", methods=["POST"])
def twilio_recording():
    ok, error = _verify_twilio_signature()
    if not ok:
        return error
    data = request.form.to_dict(flat=True) or request.get_json(silent=True) or {}
    current_app.logger.info("Twilio recording webhook received: %s", data)
    return jsonify({"success": True}), 200


@v1.route("/twilio/voice", methods=["POST", "GET"])
def twilio_voice():
    if request.method == "POST":
        ok, error = _verify_twilio_signature()
        if not ok:
            return error
    base_url = request.url_root.rstrip("/")
    recording_callback = _TWILIO_RECORDING_CALLBACK or f"{base_url}/api/v1/twilio/recording"
    transcription_callback = _TWILIO_TRANSCRIPTION_CALLBACK or f"{base_url}/api/v1/twilio/transcription"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>{_TWILIO_VOICE_PROMPT}</Say>
  <Record
    maxLength="120"
    transcribe="true"
    recordingStatusCallback="{recording_callback}"
    transcriptionCallback="{transcription_callback}"
  />
</Response>
"""
    return Response(twiml, mimetype="text/xml")


@v1.route("/twilio/transcription", methods=["POST"])
def twilio_transcription():
    ok, error = _verify_twilio_signature()
    if not ok:
        return error
    data = request.form.to_dict(flat=True) or request.get_json(silent=True) or {}

    call_sid = data.get("CallSid")
    transcription_sid = data.get("TranscriptionSid")
    transcription_text = (data.get("TranscriptionText") or "").strip()
    recording_sid = data.get("RecordingSid")
    from_number = data.get("From")
    to_number = data.get("To")
    recording_url = data.get("RecordingUrl")

    if not transcription_text:
        return jsonify({"success": True, "message": "empty_transcript"}), 200

    payload = {
        "subject": "Call transcript",
        "body": transcription_text,
        "source": "hotline",
        "provider": "twilio",
        "message_id": call_sid or transcription_sid,
        "from_email": f"tel:{from_number}" if from_number else "tel:unknown",
        "provider_thread_url": recording_url,
        "context": {
            "call_sid": call_sid,
            "transcription_sid": transcription_sid,
            "recording_sid": recording_sid,
            "to": to_number,
        },
    }

    resp, error = _post_to_intake(payload)
    if error:
        return error
    if not resp.ok:
        return jsonify({"error": "intake_failed", "status": resp.status_code}), 502

    try:
        return jsonify(resp.json()), resp.status_code
    except Exception:
        return jsonify({"success": True, "status": resp.status_code}), resp.status_code
