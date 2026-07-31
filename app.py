import os
import json
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

st.set_page_config(page_title="1957-1976 歷史文字RPG", layout="centered")
st.title("📜 第二人生：歷史的齒輪")

st.sidebar.header("🔑 系統設定")
api_key_input = st.sidebar.text_input("請輸入你的 Google AI Studio API Key", type="password")

if not api_key_input:
    st.warning("請先在左側欄位輸入您的 API Key 才能啟動遊戲。")
    st.stop()

client = genai.Client(api_key=api_key_input)

@st.cache_data
def load_configs():
    with open('game_config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    with open('historical_timeline.json', 'r', encoding='utf-8') as f:
        timeline = json.load(f)
    with open('taboo_dictionary.json', 'r', encoding='utf-8') as f:
        taboo = json.load(f)
    return config, timeline, taboo

config, timeline, taboo = load_configs()

if "game_started" not in st.session_state:
    st.session_state.game_started = False
if "player_state" not in st.session_state:
    st.session_state.player_state = None
if "current_output" not in st.session_state:
    st.session_state.current_output = None
if "game_over" not in st.session_state:
    st.session_state.game_over = False

class StatChanges(BaseModel):
    health_change: int
    sanity_change: int
    complicity_change: int

class NPCUpdate(BaseModel):
    name: str
    affinity_change: int
    moral_alignment_change: int
    status: str

class NPCUpdates(BaseModel):
    oppressor: NPCUpdate
    dependent: NPCUpdate
    ally: NPCUpdate

class GameResponse(BaseModel):
    story_text: str 
    option_A: str 
    option_B: str 
    option_C: str 
    stat_changes: StatChanges
    sensory_tags_used: list[str]
    npc_updates: NPCUpdates
    lost_assets: list[str] = Field(description="若玩家的抉擇導致某些初始資產被上繳、沒收、變賣或損毀，請在此列出該資產名稱，否則留空")

if not st.session_state.game_started:
    st.header("👤 角色創建與戶籍登記 (1957年)")
    st.write("在那個時代，你的出身與地域將決定你的一切。請謹慎選擇。")

    # 1. 選擇居住地域
    location = st.selectbox("居住地域", config["allowed_locations"], key="loc_box")
    
    # 提前取得地域規則，確保後續選單能安全呼叫 loc_rules
    loc_rules = config["constraints_matrix"]["location_rules"].get(location, {})
    
    # 2. 選擇種族 (根據地域過濾)
    allowed_eth = loc_rules.get("allowed_ethnicities", config["allowed_ethnicities"])
    ethnicity = st.selectbox("種族", allowed_eth, key="eth_box")
    
    # 3. 選擇家庭出身 (根據地域過濾禁忌出身)
    loc_forbidden_origins = loc_rules.get("forbidden_origins", [])
    all_origins = [bg["display_name"] for bg in config["allowed_backgrounds"]]
    available_origins = [o for o in all_origins if o not in loc_forbidden_origins]
    if not available_origins:
        available_origins = ["中農", "小商販"]
    origin = st.selectbox("家庭出身 (階級成分)", available_origins, key="ori_box")
    
    # 取得出身規則
    ori_rules = config["constraints_matrix"]["origin_rules"].get(origin, {})
    
    # 4. 選擇勞動崗位 (根據地域與出身雙重過濾)
    forbidden_loc_profs = loc_rules.get("forbidden_professions", [])
    forbidden_ori_profs = ori_rules.get("forbidden_professions", [])
    
    available_profs = []
    for cat, profs in config["allowed_professions"].items():
        for p in profs:
            if p not in forbidden_loc_profs and p not in forbidden_ori_profs:
                available_profs.append(p)
    if not available_profs:
        available_profs = ["街道生產組臨時工", "基層公社邊緣農民"]
        
    profession = st.selectbox("勞動崗位 (職業)", available_profs, key="prof_box")
    
    # 5. 申報個人資產 (根據地域與出身雙重過濾禁忌資產)
    st.write("申報個人資產 (可複選):")
    chosen_assets = []
    
    loc_forbidden_assets = loc_rules.get("forbidden_asset_types", [])
    ori_forbidden_assets = ori_rules.get("forbidden_asset_types", [])
    all_forbidden_assets = set(loc_forbidden_assets + ori_forbidden_assets)
    
    for a_type, a_list in config["allowed_assets"].items():
        if a_type in all_forbidden_assets:
            continue
        st.subheader(f"--- {a_type} ---")
        for asset in a_list:
            if st.checkbox(asset, key=f"asset_{asset}"):
                chosen_assets.append(asset)
    
    st.markdown("---")
    if st.button("確定登記並進入歷史", type="primary"):
        st.session_state.player_state = {
            "background": {
                "location": location,
                "ethnicity": ethnicity,
                "origin": origin,
                "profession": profession,
                "assets": chosen_assets
            },
            "hidden_stats": {"health": 80, "sanity": 70, "complicity": 0},
            "current_year": 1957,
            "game_stage": "prologue",
            "npc_roster": {
                "oppressor": {"name": "未設定", "affinity": 30, "moral_alignment": 20, "status": "alive"},
                "dependent": {"name": "未設定", "affinity": 80, "moral_alignment": 80, "status": "alive"},
                "ally": {"name": "未結識", "affinity": 60, "moral_alignment": 50, "status": "alive"}
            }
        }
        st.session_state.game_started = True
        st.rerun()
            
else:
    p_state = st.session_state.player_state
    
    if p_state["hidden_stats"]["health"] <= 0:
        st.error("【肉體枯竭】你在無盡的飢餓與肉體折磨中倒下，未能熬過這個時代。")
        st.stop()
    if p_state["current_year"] > 1976:
        st.success("【時代落幕】1976年，狂飆的歷史終於停息，你活著見證了結束。")
        st.stop()

    def run_turn(choice_text=""):
        year = str(p_state["current_year"])
        historical_fact = timeline.get(year, timeline["1957"])
        
        system_instruction = f"""
        你是一位頂級文字RPG導演。請嚴格遵守以下時代禁忌詞彙對照表：
        {json.dumps(taboo, ensure_ascii=False)}
        絕對禁止使用宏觀歷史定性名詞。客觀化感官拆解，提供3個純物理動作選項。
        【資產管理鐵律】：如果玩家的抉擇涉及交出、上繳、被沒收或變賣其擁有的資產（例如手錶、糧票等），你必須在 `lost_assets` 欄位中精確列出該資產名稱，確保其從背包中除名。
        """
        
        prompt = f"""
        【目前歷史齒輪】：{json.dumps(historical_fact, ensure_ascii=False)}
        【玩家背景】：{json.dumps(p_state["background"], ensure_ascii=False)}
        【玩家狀態】：{json.dumps(p_state["hidden_stats"], ensure_ascii=False)}
        【上一步抉擇】：{choice_text if choice_text else "歷史開局，序章啟動。"}
        請生成故事、選項與狀態更新。
        """
        
        with st.spinner("⏳ 歷史的齒輪正在運轉，AI 正在生成故事..."):
            response = client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=GameResponse,
                    temperature=0.75,
                ),
            )
            
            output = json.loads(response.text)
            st.session_state.current_output = output
            
            changes = output["stat_changes"]
            p_state["hidden_stats"]["health"] = max(0, min(100, p_state["hidden_stats"]["health"] + changes["health_change"]))
            p_state["hidden_stats"]["sanity"] = max(0, min(100, p_state["hidden_stats"]["sanity"] + changes["sanity_change"]))
            p_state["hidden_stats"]["complicity"] = max(0, min(100, p_state["hidden_stats"]["complicity"] + changes["complicity_change"]))

            # 🌟【資產動態扣除】若 AI 判定該回合失去了某些資產，從背包中永久移除
            if "lost_assets" in output and output["lost_assets"]:
                current_assets = p_state["background"]["assets"]
                for item in output["lost_assets"]:
                    if item in current_assets:
                        current_assets.remove(item)
            
            if p_state["game_stage"] == "prologue":
                p_state["current_year"] = 1958
                p_state["game_stage"] = "main_flow"
            else:
                p_state["current_year"] += 1

    if st.session_state.current_output is None:
        run_turn()
        st.rerun()

    st.markdown(f"### 📍 當前年份：{p_state['current_year']} 年")

    # 顯示當前剩餘資產供玩家隨時檢視
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎒 當前隨身資產")
    for asset in p_state["background"]["assets"]:
        st.sidebar.markdown(f"- {asset}")
    
    h, s, c = p_state["hidden_stats"]["health"], p_state["hidden_stats"]["sanity"], p_state["hidden_stats"]["complicity"]
    
    dynamic_css = "<style>"
    has_anomaly = False
    
    if h <= 40:
        has_anomaly = True
        # 肉體枯竭：畫面整體褪為灰白、出現暗角
        dynamic_css += """
        .stApp {
            filter: grayscale(70%) contrast(120%);
        }
        """
        st.warning("⚠️ 【視覺異變】螢幕邊緣出現深度暗角，畫面色彩褪為灰白...")
        
    if s <= 35:
        has_anomaly = True
        # 雙重思想崩潰：文字與關鍵名詞產生血紅色閃爍特效
        dynamic_css += """
        @keyframes bloodFlash {
            0% { color: inherit; }
            50% { color: #ff2b2b; text-shadow: 0 0 8px rgba(255, 0, 0, 0.8); }
            100% { color: inherit; }
        }
        .stMarkdown p, .stMarkdown li {
            animation: bloodFlash 5s infinite;
        }
        """
        st.warning("⚠️ 【視覺異變】排版錯位失調，關鍵字句泛起血色脈動...")
        
    if c >= 40:
        has_anomaly = True
        # 共業沾血：背景底層滲出洗不掉的暗褐色墨暈
        dynamic_css += """
        .stApp {
            background-color: #2b1810 !important;
            transition: background-color 2s ease;
        }
        """
        st.error("⚠️ 【視覺異變】螢幕底層滲出無法洗刷的暗褐色墨暈印記...")
        
    dynamic_css += "</style>"
    
    if has_anomaly:
        st.markdown(dynamic_css, unsafe_allow_html=True)

    output = st.session_state.current_output
    st.markdown("---")
    st.write(output["story_text"])
    st.markdown("---")

    st.subheader("🤔 你的抉擇：")
    if st.button(output["option_A"]):
        run_turn(output["option_A"])
        st.rerun()
    if st.button(output["option_B"]):
        run_turn(output["option_B"])
        st.rerun()
    if st.button(output["option_C"]):
        run_turn(output["option_C"])
        st.rerun()
