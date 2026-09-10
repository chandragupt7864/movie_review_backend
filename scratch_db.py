from app.database import get_db_cursor

with get_db_cursor(commit=True) as cursor:
    cursor.execute("""
        UPDATE movie_review_pipeline
        SET voice_status = 'COMPLETED',
            voice_audio_path = 'storage/audio/dummy.mp3',
            next_agent = 'VIDEO_DOWNLOADER_AGENT',
            video_download_status = 'PENDING'
        WHERE id = 173
    """)
print("Updated Moana (ID 173) to pending video download status!")
