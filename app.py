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

# 🌟 升級版 Response 結構，加入 lost_assets
class GameResponse(BaseModel):
    story_text: str 
    option_A: str 
    option_B: str 
    option_C: str 
    stat_changes: StatChanges
    sensory_tags_used: list[str]
    npc_updates: NPCUpdates
    assets_lost_from_previous_choice: list[str] = Field(
        description="🛑 嚴格判定：只能根據玩家的【上一步抉擇】來結算！若上一步抉擇導致實質失去資產，填入名稱。若無，或是資產『現在』才面臨威脅（玩家還沒選），務必回傳 []！絕對禁止超前沒收！"
    )

if not st.session_state.game_started:
    st.header("👤 角色創建與戶籍登記 (1957年)")
    st.write("在那個時代，你的出身與地域將決定你的一切。請謹慎選擇。")

    location = st.selectbox("居住地域", config["allowed_locations"], key="loc_box")
    loc_rules = config["constraints_matrix"]["location_rules"].get(location, {})
    
    allowed_eth = loc_rules.get("allowed_ethnicities", config["allowed_ethnicities"])
    ethnicity = st.selectbox("種族", allowed_eth, key="eth_box")
    
    loc_forbidden_origins = loc_rules.get("forbidden_origins", [])
    all_origins = [bg["display_name"] for bg in config["allowed_backgrounds"]]
    available_origins = [o for o in all_origins if o not in loc_forbidden_origins]
    if not available_origins:
        available_origins = ["中農", "小商販"]
    origin = st.selectbox("家庭出身 (階級成分)", available_origins, key="ori_box")
    
    ori_rules = config["constraints_matrix"]["origin_rules"].get(origin, {})
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
    if p_state["hidden_stats"]["complicity"] >= 100:
        st.error("【靈魂湮滅】為了活下去，你出賣了恩人、陷害了無辜，雙手沾滿了洗不掉的血污。你確實熬過了這個時代，但『你』已經死了，活下來的，只是一個時代的怪物。")
        st.stop()    
    if p_state["current_year"] > 1976:
        st.success("【時代落幕】1976年，狂飆的歷史終於停息，你活著見證了結束。")
        st.stop()

    def run_turn(choice_text=""):
        year = str(p_state["current_year"])
        historical_fact = timeline.get(year, timeline["1957"])
        
        # 🌟 劇本狀態機：根據年份與進度，動態注入「導演私下指令」與「段落一規則」
        special_directive = ""
        paragraph_one_rule = ""
        
        if p_state["game_stage"] == "prologue":
            # 1957年開局：百花齊放陷阱 + 日常生活描寫
            special_directive = """
            【動態序章鐵律：百花齊放的溫柔陷阱（極機密）】：
            這是遊戲的開局（1957年）。請為玩家設計一個充滿希望與鼓勵言論自由氛圍的場景（如：座談會、意見徵集、領導談心）。
            你的文本必須溫情脈脈，而你提供的 3 個物理選項，必須刻意迎合「現代人的常識與普世價值」（例如：提出建設性批評、反映基層真實困難、追求個人理想）。
            絕對不要在文本中暗示危機，讓現代玩家毫無防備地踩入陷阱。
            """
            paragraph_one_rule = "[段落一（日常底色）]：作為故事開局，請用1-2句充滿感官細節的文學語言，描寫玩家當下基於其【背景與資產】的日常生活狀態（例如勞動的汗水、手錶的滴答聲、或是家中的氣味），作為時代風暴前的寧靜。"
            
        else:
            # 1958年及以後：常規過渡
            paragraph_one_rule = "[段落一（蒙太奇餘波）]：用1-2句充滿感官細節的文學語言，描寫「上一步抉擇」在隨後幾個月裡帶來的餘波、磨耗或短暫平靜，展現時間的殘酷流逝。"
            
            if p_state["current_year"] == 1958 and choice_text:
                # 1958年的專屬歷史悶棍
                special_directive = """
                【歷史悶棍鐵律：反右清算與風向突變（極機密）】：
                玩家剛剛做出了1957年「百花齊放」時期的選項。現在是1958年，政治風向突變！
                請在第一段中，用最殘酷的史實擊碎玩家的現代思維：他們上一步看似合理的建議，現在被定性為「惡毒攻擊、右派言論」或遭到群眾的嚴厲批鬥。
                請剝奪相關資產，讓玩家徹底感受時代的無力感。隨後切入1958年的新危機。
                """

        system_instruction = f"""
        角色：頂級文字RPG導演與純文學作家。
        禁忌詞：{json.dumps(taboo, ensure_ascii=False)}（絕對禁止使用宏觀定性名詞，需用客觀感官拆解描寫）
        
        【【敘事與排版結構】
        請嚴格輸出三段無標題純文字，段落間以 `\n\n` 分隔：
        {paragraph_one_rule}
        2. 時代氣候（最重要，請用極大篇幅擴寫）：不要只寫表面事件。請用白描手法，極度細膩地刻畫當前年份【目前歷史齒輪】的環境氣味、天空的陰霾、群眾狂熱或恐懼的神態、以及社區中令人窒息的社會氛圍。
        3. 命運迫近：將時代的宏大危機，具象化為眼前逼迫玩家的一件微小卻致命的日常衝突，引出接下來的 3 個物理抉擇。
        
        【選項與數值設計】
        1. 數值克制：單次變動限制在 -15 到 +15。
        2. 黑暗三角折衷：選項必須體現生存代價（例：出賣他人換取健康但增加共業；堅守道德維持理智但損害健康）。
        3. 資產破局：若玩家持有特殊資產，請設計一個「消耗該資產」來化解危機的選項。
        
        {special_directive}
        """
        
        prompt = f"""
        【當下年份】：{p_state["current_year"]} 年
        【目前歷史齒輪】：{json.dumps(historical_fact, ensure_ascii=False)}
        【玩家狀態與資產】：{json.dumps(p_state["hidden_stats"], ensure_ascii=False)} | {json.dumps(p_state["background"], ensure_ascii=False)}
        【上一步抉擇】：{choice_text if choice_text else "遊戲開始。"}
        
        請依照 JSON 結構 (GameResponse) 輸出。注意：`assets_lost_from_previous_choice` 僅能基於【上一步抉擇】結算，絕對禁止超前扣除！
        """
        
        prompt = f"""
        【當下年份】：{p_state["current_year"]} 年
        【目前歷史齒輪（新事件）】：{json.dumps(historical_fact, ensure_ascii=False)}
        【玩家背景與資產】：{json.dumps(p_state["background"], ensure_ascii=False)}
        【玩家狀態】：{json.dumps(p_state["hidden_stats"], ensure_ascii=False)}
        【上一步抉擇（數月前發生）】：{choice_text if choice_text else "歷史開局，序章啟動。"}
        
        請嚴格遵照【文學過渡與排版鐵律】的 `\\n\\n` 換行格式（絕不輸出標題），生成具備龐大信息量與沉浸感的故事。
        """
        
        with st.spinner("⏳ 歷史的齒輪正在運轉，正在推演故事..."):
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=GameResponse,
                    temperature=0.75,
                ),
            )
            
            raw_text = response.text
            
            # 1. 預防 AI 手癢加上 Markdown 標記
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "", 1).removesuffix("```")
            elif raw_text.startswith("```"):
                raw_text = raw_text.replace("```", "", 1).removesuffix("```")
                
            output = json.loads(raw_text.strip())
            
            if "GameResponse" in output:
                output = output["GameResponse"]
                
            st.session_state.current_output = output
            
            # 3. 防禦性提取數值
            changes = output.get("stat_changes", {"health_change": 0, "sanity_change": 0, "complicity_change": 0})
            
            raw_h_change = changes.get("health_change", 0)
            raw_s_change = changes.get("sanity_change", 0)
            raw_c_change = changes.get("complicity_change", 0)
            
            # 🌟 時代的麻木（殘血保護機制）：當健康或理智低於 30 時，扣減傷害減半，模擬求生本能與心理麻木
            current_h = p_state["hidden_stats"]["health"]
            current_s = p_state["hidden_stats"]["sanity"]
            
            actual_h_change = int(raw_h_change / 2) if raw_h_change < 0 and current_h <= 30 else raw_h_change
            actual_s_change = int(raw_s_change / 2) if raw_s_change < 0 and current_s <= 30 else raw_s_change
            
            # 結算數值
            p_state["hidden_stats"]["health"] = max(0, min(100, current_h + actual_h_change))
            p_state["hidden_stats"]["sanity"] = max(0, min(100, current_s + actual_s_change))
            p_state["hidden_stats"]["complicity"] = max(0, min(100, p_state["hidden_stats"]["complicity"] + raw_c_change))
            
            # 🌟 4. 智能資產銷毀系統 (終極防護版)
            # 使用新的變數名稱來接收資料
            lost_assets = output.get("assets_lost_from_previous_choice", [])
            
            # 防呆機制：在序章（生成第一回合故事時），玩家尚未做出選擇，強制忽略
            if lost_assets and p_state["game_stage"] != "prologue":
                current_assets = p_state["background"]["assets"]
                items_to_remove = []
                for lost_item in lost_assets:
                    for actual_asset in current_assets:
                        if lost_item in actual_asset or actual_asset in lost_item:
                            items_to_remove.append(actual_asset)
                
                for item in set(items_to_remove):
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
        dynamic_css += ".stApp { filter: grayscale(70%) contrast(120%); }"
        st.warning("⚠️ 【視覺異變】螢幕邊緣出現深度暗角，畫面色彩褪為灰白...")
    if s <= 35:
        has_anomaly = True
        # 使用多行字串 (Triple quotes) 讓 CSS 更容易閱讀與修改
        dynamic_css += """
        @keyframes bloodGlitch {
            0%, 90%, 100% { 
                transform: translate(0, 0) skew(0deg); 
                color: #ff4d4d; /* 持續維持清晰的紅色 */
                text-shadow: 0 0 2px rgba(255, 0, 0, 0.3); 
            }
            92% { 
                transform: translate(-3px, 1px) skew(2deg); 
                color: #ff0000; 
                text-shadow: 2px 2px 0px rgba(139, 0, 0, 0.8); 
            }
            94% { 
                transform: translate(3px, -2px) skew(-2deg); 
                color: #ff4d4d; 
                text-shadow: -2px -1px 0px rgba(139, 0, 0, 0.8); 
            }
            96% { 
                transform: translate(-1px, 3px) skew(1deg); 
                color: #ff0000; 
                text-shadow: 0 0 5px rgba(255, 0, 0, 1); 
            }
            98% { 
                transform: translate(2px, -1px) skew(-1deg); 
                color: #ff4d4d; 
                text-shadow: none; 
            }
        }
        .stMarkdown p, .stMarkdown li { 
            color: #ff4d4d !important; /* 強制覆蓋原本字體顏色 */
            animation: bloodGlitch 4s infinite normal; /* 每4秒發作一次，發作時間極短 */
        }
        """
        st.warning("⚠️ 【視覺異變】排版錯位失調，文字彷彿被撕裂般抽搐...")
    if c >= 40:
        has_anomaly = True
        dynamic_css += ".stApp { background-color: #2b1810 !important; transition: background-color 2s ease; }"
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
