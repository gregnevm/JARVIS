from app.media import extract_audio_media


def test_voice():
    m = extract_audio_media({"voice": {"file_id": "v1", "mime_type": "audio/ogg"}})
    assert m is not None and m.source == "voice" and m.file_id == "v1"


def test_audio_track():
    m = extract_audio_media(
        {"audio": {"file_id": "a1", "mime_type": "audio/mpeg", "title": "Song"}}
    )
    assert m is not None and m.source == "audio" and m.title == "Song"


def test_video_note():
    m = extract_audio_media({"video_note": {"file_id": "vn1"}})
    assert m is not None and m.source == "video_note"


def test_video():
    m = extract_audio_media({"video": {"file_id": "vid1", "mime_type": "video/mp4"}})
    assert m is not None and m.source == "video"


def test_audio_document():
    m = extract_audio_media(
        {
            "document": {
                "file_id": "d1",
                "mime_type": "audio/flac",
                "file_name": "track.flac",
            }
        }
    )
    assert m is not None and m.source == "document"


def test_photo_not_audio():
    assert extract_audio_media({"photo": [{"file_id": "p1"}]}) is None
