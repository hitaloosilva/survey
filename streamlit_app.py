import os
import json
import hashlib
from datetime import datetime
import pandas as pd
import streamlit as st
from g_drive_service import GoogleDriveService, GoogleDriveServiceDict
from io import BytesIO

CRED_PATH = "sheet_credential.json"
CASES_PATH = "simulated_cases"
RESPONSES_PATH = "responses.csv"

MEDS = ["RAASi", "BB", "MRA", "SGLT2i"]
ACTION_CHOICES = ["no_change", "initiate", "up-titrate", "down-titrate", "stop"]
resp = None


# Streamlit secreats to ByteIO stream for g_drive_service
def streamlit_secrets_to_bytesio(key: str) -> BytesIO:
    if key not in st.secrets:
        raise KeyError(f"Key '{key}' not found in Streamlit secrets.")
    
    data = st.secrets[key]    
    json_str = json.dumps(dict(data))

    byte_stream = BytesIO(json_str.encode('utf-8'))
    byte_stream.seek(0)
    return dict(data)
    

def _safe_get(row: pd.Series, col: str, default=""):
    v = row.get(col, default)
    if pd.isna(v):
        return default
    return v

def ensure_case_id(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "Case_ID" not in df.columns:
        if ("Pat_ID" in df.columns) and ("Obs" in df.columns):
            df["Case_ID"] = df["Pat_ID"].astype(str) + "-" + df["Obs"].astype(str)
        elif "Pat_ID" in df.columns:
            df["Case_ID"] = df["Pat_ID"].astype(str)
        else:
            df["Case_ID"] = df.index.astype(str)
    return df

#@st.cache_data(show_spinner=False)
#def load_cases(path: str) -> pd.DataFrame:
#    if not os.path.exists(path):
#        raise FileNotFoundError(f"Missing {path}. Put cases.csv in Drive and set CASES_PATH.")
#    df = pd.read_csv(path)
#    df = ensure_case_id(df)
#    return df.reset_index(drop=True)
    
@st.cache_data(show_spinner=False)
def load_cases(path: str, cred_path:str) -> pd.DataFrame:
    selected_fields="files(id,name,webViewLink)"
    #g_drive_service=GoogleDriveService(cred_path).build_drive()
    stream = streamlit_secrets_to_bytesio('sheet_api')
    g_drive_service=GoogleDriveServiceDict(stream).build_drive()

    list_file=g_drive_service.files().list(fields=selected_fields).execute()
    print(list_file.get("files"))

    #client = GoogleDriveService(cred_path).build_sheet()
    client = GoogleDriveServiceDict(stream).build_sheet()
    spreadsheet = client.open(path) 
    worksheet = spreadsheet.sheet1 
    worksheet_data = worksheet.get_all_records()
    df = pd.DataFrame(worksheet_data)
    #if not os.path.exists(path):
    #    raise FileNotFoundError(f"Missing {path}. Put cases.csv in Drive and set CASES_PATH.")
    
    df = ensure_case_id(df)
    return df.reset_index(drop=True)

#def append_response(path: str, payload: dict):
#    df_row = pd.DataFrame([payload])
#    write_header = not os.path.exists(path)
#    df_row.to_csv(path, mode="a", header=write_header, index=False)
    
def append_response(path: str, payload: dict, cred_path:str):
    stream = streamlit_secrets_to_bytesio('sheet_api')
    client = GoogleDriveServiceDict(stream).build_sheet()
    
    #client = GoogleDriveService(cred_path).build_sheet()
    
    # Accessing the desired spreadsheet 
    spreadsheet = client.open(path) 
    worksheet = spreadsheet.sheet1 
    # Appending the data 
    payload_list = [payload.get(col, "") for col in ["timestamp", "reviewer", "Case_ID", "agree", "engine_Action"] + [f"dr_Action_{m}" for m in MEDS] + ["dr_AssessmentPlan"]]  
    worksheet.append_row(payload_list) 

def _normalize_age_sex(row: pd.Series):
    age = _safe_get(row, "Age", _safe_get(row, "age", ""))
    sex = _safe_get(row, "Sex", _safe_get(row, "sex", ""))
    try:
        if age != "":
            age = int(float(age))
    except Exception:
        pass
    sex_str = str(sex).strip()
    if sex_str.lower() in ["m", "male"]:
        sex_str = "male"
    elif sex_str.lower() in ["f", "female"]:
        sex_str = "female"
    return age, sex_str

def _bool01(x):
    try:
        return int(float(x)) == 1
    except Exception:
        return False

def summarize_case(row: pd.Series) -> str:
    age, sex = _normalize_age_sex(row)
    intro = f"{age} years old {sex} with HFrEF in your telehealth clinic." if (age != "" or sex != "") else "Patient with HFrEF in your telehealth clinic."

    # Exactly your formatting (multiline)
    vitals = f"Vitals: SBP {_safe_get(row,'SBP','?')}, HR {_safe_get(row,'HR','?')}"
    tir = f"TIR: low SBP {_safe_get(row,'TIR_low_sys','?')}%, low HR {_safe_get(row,'TIR_low_HR','?')}%"

    sx_hyp = "yes" if _bool01(_safe_get(row, "Sx_hypot", 0)) else "no"
    sx_brd = "yes" if _bool01(_safe_get(row, "Sx_brady", 0)) else "no"
    sx = f"Symptoms: hypotension {sx_hyp}, bradycardia {sx_brd}"

    labs = f"Labs: K {_safe_get(row,'K','?')}, Cr {_safe_get(row,'Cr','?')}, Cr % change {_safe_get(row,'Cr_pct_ch','?')}, eGFR {_safe_get(row,'GFR','?')}"

    meds = (
        "GDMT dose levels (0–4): "
        f"RAASi {_safe_get(row,'RAASi',0)} | "
        f"BB {_safe_get(row,'BB',0)} | "
        f"MRA {_safe_get(row,'MRA',0)} | "
        f"SGLT2i {_safe_get(row,'SGLT2i',0)}"
    )

    action = str(_safe_get(row, "Action", "no_change")).strip()
    rec = f"Recomended action: '{action}'"

    return "\n".join([intro, vitals, tir, sx, labs, meds, rec])

def default_alt_actions_from_engine(row: pd.Series) -> dict:
    out = {m: "no_change" for m in MEDS}
    for m in MEDS:
        col = f"Action_{m}"
        if col in row.index:
            v = str(_safe_get(row, col, "no_change"))
            v = v.replace("uptitration", "up-titrate").replace("downtitration", "down-titrate")
            v = v.replace("initiation", "initiate").replace("discontinuation", "stop")
            if v in ACTION_CHOICES:
                out[m] = v
    return out

def shared_case_indices(df: pd.DataFrame, overlap_frac: float = 0.20) -> list:
    n = len(df)
    k = max(1, int(round(overlap_frac * n)))
    scores = []
    for i, cid in enumerate(df["Case_ID"].astype(str).tolist()):
        h = hashlib.md5(cid.encode("utf-8")).hexdigest()
        scores.append((h, i))
    scores.sort(key=lambda t: t[0])
    return [i for _, i in scores[:k]]

st.set_page_config(page_title="Telehealt GDMT optimization", layout="wide")
st.title("Telehealt GDMT optimization")

cases = load_cases(CASES_PATH, CRED_PATH)

with st.sidebar:
    st.header("Session")
    reviewer = st.text_input("Reviewer initials / ID", value=st.session_state.get("reviewer", ""))
    st.session_state["reviewer"] = reviewer

    randomize = st.checkbox("Randomize case order", value=st.session_state.get("randomize", True))
    st.session_state["randomize"] = randomize

    st.caption("~20% of cases are shared across reviewers by design.")

    if "case_order" not in st.session_state or st.button("Restart"):
        import random
        shared_idx = shared_case_indices(cases, overlap_frac=0.20)
        remaining = [i for i in range(len(cases)) if i not in set(shared_idx)]
        if randomize:
            random.shuffle(shared_idx)
            random.shuffle(remaining)
        st.session_state["case_order"] = shared_idx + remaining
        st.session_state["case_idx"] = 0

    total = len(cases)
    idx = int(st.session_state.get("case_idx", 0))
    idx = max(0, min(idx, total - 1))
    st.session_state["case_idx"] = idx

    st.progress((idx + 1) / total if total else 0)
    st.caption(f"Case {idx + 1} of {total}")

    jump = st.number_input("Jump to case #", min_value=1, max_value=max(1, total), value=idx + 1, step=1)
    if st.button("Go"):
        st.session_state["case_idx"] = int(jump) - 1
        st.rerun()

order = st.session_state["case_order"]
row = cases.iloc[order[st.session_state["case_idx"]]]
case_id = str(_safe_get(row, "Case_ID", ""))

colA, colB = st.columns([1.25, 1.0], gap="large")

with colA:
    st.subheader(f"Case {case_id}")
    st.code(summarize_case(row), language="text")

with colB:
    st.subheader("Physician response")

    agree = st.radio("Do you agree with the recommended action?", ["Agree", "Disagree"], horizontal=True)
    alt_defaults = default_alt_actions_from_engine(row)

    st.markdown("**If Disagree: choose your alternative actions**")
    alt_actions = {}
    for m in MEDS:
        alt_actions[m] = st.selectbox(
            f"{m}",
            ACTION_CHOICES,
            index=ACTION_CHOICES.index(alt_defaults.get(m, "no_change")),
            key=f"alt_{case_id}_{m}",
            disabled=(agree == "Agree"),
        )

    # ALWAYS enabled (per your request)
    ap_text = st.text_area(
        "Assessment and Plan (action rationale, 3 sentences max)",
        value="",
        height=140,
        placeholder="Max 3 sentences: assessment + your plan + key rationale.",
    )

    if st.button("Save response", type="primary"):
        if reviewer.strip() == "":
            st.error("Please enter Reviewer initials/ID in the sidebar.")
        elif agree == "Disagree" and ap_text.strip() == "":
            st.error("Assessment and Plan is required when you disagree.")
        else:
            payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "reviewer": reviewer.strip(),
                "Case_ID": case_id,
                "agree": 1 if agree == "Agree" else 0,
                "engine_Action": str(_safe_get(row, "Action", "no_change")),
                **{f"dr_Action_{m}": alt_actions[m] for m in MEDS},
                "dr_AssessmentPlan": ap_text.strip(),
            }
            append_response(RESPONSES_PATH, payload, CRED_PATH)
            st.success(f"Saved to {RESPONSES_PATH}")
            resp = load_cases(RESPONSES_PATH, CRED_PATH)

    if st.button("Next case ➜"):
        st.session_state["case_idx"] = min(st.session_state["case_idx"] + 1, len(cases) - 1)
        st.rerun()

st.divider()
st.subheader("Responses")
resp = load_cases(RESPONSES_PATH, CRED_PATH)
if resp is not None and len(resp) > 0:
    # FILTER BY REVIEWER
    if reviewer.strip() != "":
        resp = resp[resp["REVIEWER"] == reviewer.strip()]
        # drop time and reviewer columns for better readability
        resp = resp.drop(columns=["TIME", "REVIEWER", "Case_ID"], errors="ignore")
        print(resp)
        st.dataframe(resp.tail(50), use_container_width=True)
        st.download_button(
            "Download responses.csv",
            data=resp.to_csv(index=False).encode("utf-8"),
            file_name="responses.csv",
            mime="text/csv",
        )
    else:
        st.info("No responses saved yet.")    
else:
    st.info("No responses saved yet.")
