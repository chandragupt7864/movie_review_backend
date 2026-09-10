class MusicCopyrightAssessmentService:
    def assess(
        self,
        technical_metadata: dict,
        embedded_metadata: dict,
        recognition_result: dict,
        trusted_track: dict | None = None,
    ) -> dict:
        if trusted_track and trusted_track.get("copyright_status") in {"VERIFIED_SAFE", "ATTRIBUTION_REQUIRED"}:
            status = trusted_track["copyright_status"]
            return {
                "copyright_status": status,
                "copyright_risk_level": "LOW",
                "license_type": trusted_track.get("license_type"),
                "attribution_required": bool(trusted_track.get("attribution_required")),
                "attribution_text": trusted_track.get("attribution_text"),
                "reason": "License inherited from a previously verified track fingerprint.",
                "source_type": trusted_track.get("source_type"),
                "source_reference": trusted_track.get("source_reference"),
                "analysis_data": {"license_inherited_from_verified_track": True},
            }

        status = str(recognition_result.get("status") or "UNKNOWN")
        if status == "IDENTIFIED":
            return {
                "copyright_status": "LIKELY_COPYRIGHTED",
                "copyright_risk_level": "HIGH",
                "license_type": None,
                "attribution_required": False,
                "attribution_text": None,
                "reason": "Track identified, but no verified usage license exists in this library.",
                "source_type": None,
                "source_reference": None,
                "analysis_data": {"identified_track_without_license": True},
            }

        _ = technical_metadata, embedded_metadata
        return {
            "copyright_status": "UNKNOWN",
            "copyright_risk_level": "UNKNOWN",
            "license_type": None,
            "attribution_required": False,
            "attribution_text": None,
            "reason": "No reliable license conclusion could be made from the available evidence.",
            "source_type": None,
            "source_reference": None,
            "analysis_data": {
                "defaulted_to_unknown": True,
                "recognition_warning": recognition_result.get("warning"),
            },
        }
