from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL


def get_supabase_client() -> Client:
	if not SUPABASE_URL or not SUPABASE_KEY:
		raise RuntimeError("SUPABASE_URL/SUPABASE_KEY are not configured")
	return create_client(SUPABASE_URL, SUPABASE_KEY)


def save_lead(payload: dict[str, Any], table: str = "leads") -> dict[str, Any]:
	client = get_supabase_client()
	response = client.table(table).insert(payload).execute()
	return {
		"status_code": response.status_code,
		"count": len(response.data or []),
		"data": response.data,
	}
