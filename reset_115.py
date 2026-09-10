from app.database import get_db_cursor

def reset_movie_115():
    with get_db_cursor(commit=True) as cursor:
        # Check current state first
        cursor.execute("""
            SELECT id, movie_title, master_video_path, voice_audio_path, render_status, voice_status, shorts_status, next_agent, overall_status, is_active, is_locked 
            FROM movie_review_pipeline 
            WHERE id = 115
        """)
        row = cursor.fetchone()
        if not row:
            print("Movie 115 not found in the database.")
            return

        print("Current Status of Movie 115:")
        for k, v in row.items():
            print(f"  {k}: {v}")

        # Perform the update/reset
        cursor.execute("""
            UPDATE movie_review_pipeline
            SET 
                is_active = True,
                is_locked = False,
                next_agent = 'SHORTS_COMPOSER_AGENT',
                shorts_status = 'PENDING',
                overall_status = 'MASTER_VIDEO_READY',
                render_status = 'COMPLETED',
                voice_status = 'COMPLETED'
            WHERE id = 115
        """)
        print("\nMovie 115 reset successful!")

        # Verify state
        cursor.execute("""
            SELECT id, movie_title, master_video_path, voice_audio_path, render_status, voice_status, shorts_status, next_agent, overall_status, is_active, is_locked 
            FROM movie_review_pipeline 
            WHERE id = 115
        """)
        row = cursor.fetchone()
        print("\nNew Status of Movie 115:")
        for k, v in row.items():
            print(f"  {k}: {v}")

if __name__ == "__main__":
    reset_movie_115()
