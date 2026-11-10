"""Optional Streamlit client. Start the FastAPI backend in a separate terminal."""

import json
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

from project_backend.config import ClientSettings


def call_api(base_url: str, method: str, path: str, **kwargs: Any) -> dict[str, Any] | None:
    try:
        with httpx.Client(base_url=base_url, timeout=15) as client:
            response = client.request(method, path, **kwargs)
        if response.is_error:
            body = response.json()
            error = body.get("error", {})
            st.warning(error.get("message", f"Backend returned HTTP {response.status_code}."))
            st.json(body)
            return None
        return response.json()
    except httpx.RequestError:
        st.error("Cannot reach the backend. Start it using the README commands and check the URL.")
    except ValueError:
        st.error("Backend returned a non-JSON response. Check that this URL points to the API.")
    return None


def main() -> None:
    st.set_page_config(page_title="ML Project Starter", page_icon="☀️", layout="wide")
    st.title("Solar Forecast / General ML — Project Starter")
    st.info("Planning scaffold: no real dataset, trained model, or live provider is configured.")
    base_url = st.sidebar.text_input("Backend URL", ClientSettings().backend_url).rstrip("/")
    page = st.sidebar.radio("Page", ["Overview", "Validate data", "Forecast", "Planning"])

    if page == "Overview":
        st.subheader("Backend configuration")
        profile = call_api(base_url, "GET", "/api/v1/project")
        status = call_api(base_url, "GET", "/api/v1/status")
        if profile is not None:
            st.json(profile)
        if status is not None:
            st.json(status)
        st.caption("These are implementation defaults, not a finalized problem statement.")

    elif page == "Validate data":
        mode = st.radio("Input purpose", ["historical", "inference"], horizontal=True)
        st.caption("Historical data includes the target; future/inference data must exclude it.")
        sample = Path("data/sample/solar_history.csv")
        if sample.exists():
            st.download_button(
                "Download synthetic solar CSV example",
                sample.read_bytes(),
                file_name=sample.name,
                mime="text/csv",
            )
        upload = st.file_uploader("UTF-8 CSV with a header", type=["csv"])
        if st.button("Validate CSV", disabled=upload is None) and upload is not None:
            result = call_api(
                base_url,
                "POST",
                "/api/v1/data/validate/csv",
                params={"mode": mode},
                files={"file": ("upload.csv", upload.getvalue(), "text/csv")},
            )
            if result is not None:
                if result["valid"]:
                    st.success(
                        "Schema passed; this does not certify data quality or model readiness."
                    )
                else:
                    st.error("Fix the listed validation issues.")
                st.json(result)

    elif page == "Forecast":
        st.caption(
            "A valid request returns HTTP 503 until a real predictor is registered. "
            "No forecast is fabricated."
        )
        example = Path("data/sample/forecast_request.json")
        default = example.read_text(encoding="utf-8") if example.exists() else '{"records": []}'
        raw = st.text_area("Inference request JSON", default, height=300)
        if st.button("Send forecast request"):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                st.error("Enter valid JSON first.")
            else:
                result = call_api(base_url, "POST", "/api/v1/forecast", json=payload)
                if result is not None:
                    st.dataframe(result["predictions"], use_container_width=True)
                    st.json(result)

    else:
        st.markdown("""
### Decide before implementing ML
1. Identify the first user and their measurable problem.
2. Choose a licensed dataset or authorized API with a measured target.
3. Confirm target meaning, units, location/timezone, and input availability.
4. Agree on the prediction horizon and chronological evaluation boundary.
5. Update the profile, freeze a data snapshot, and evaluate a simple baseline.
6. Add the model adapter; add retrieval/agent features only after forecasting works.

See `docs/PROJECT_DECISIONS.md`, `docs/BACKEND_GUIDE.md`, and
`docs/PUBLISHING_GUIDE.md` in the repository.
""")
    st.caption("Educational/advisory only. This application does not control grid hardware.")


if __name__ == "__main__":
    main()
