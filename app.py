import datetime
import json
from pathlib import Path
import streamlit as st
import requests
import subprocess

# Configuration de la page Streamlit pour mobile et PC
st.set_page_config(
    page_title="Analyse & Stratégie PMU",
    page_icon="🐎",
    layout="wide",
    initial_sidebar_state="expanded"
)

DOSSIER = Path("application_jeux_pmu")
DOSSIER.mkdir(parents=True, exist_ok=True)
FICHIER_HISTORIQUE = DOSSIER / "historique_bilan_pmu.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
}

# --- FONCTION DE SYNCHRONISATION AUTOMATIQUE GITHUB ---

def sauvegarder_et_synchroniser(data, filename, message="Mise à jour automatique des données PMU"):
    # 1. Enregistrement local sur le serveur / disque
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 2. Envoi automatique sur GitHub si le token est configuré dans Streamlit Secrets
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            
            subprocess.run(["git", "config", "--global", "user.email", "bot@streamlit.app"], capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name", "Streamlit Bot"], capture_output=True)
            
            subprocess.run(["git", "add", str(filename)], check=True, capture_output=True)
            
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if filename.name in status.stdout or str(filename) in status.stdout:
                subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
                
                repo_url = f"https://{token}@github.com/antholetest/chevaux.git"
                res_push = subprocess.run(["git", "push", repo_url], capture_output=True, text=True)
                if res_push.returncode != 0:
                    subprocess.run(["git", "push", repo_url, "HEAD"], capture_output=True)
                
                st.toast("Données sauvegardées et synchronisées sur GitHub !", icon="✅")
    except Exception:
        # En local (sans secrets.toml), l'enregistrement local a fonctionné, on prévient simplement sans bloquer
        st.toast("Données enregistrées localement (mode hors ligne).", icon="💾")
# --- FONCTIONS MÉTIER ---

def telecharger_pmu_date(date_iso, fichier_cible):
    dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
    date_pmu = dt.strftime("%d%m%Y")

    url_programme = f"https://online.turfinfo.api.pmu.fr/rest/client/7/programme/{date_pmu}"
    try:
        res = requests.get(url_programme, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return False
        data = res.json()
    except Exception:
        return False

    reunions = data.get("programme", {}).get("reunions", [])
    if not reunions:
        return False

    resultats_journee = []
    for reunion in reunions:
        num_r = f"R{reunion.get('numOfficiel')}"
        hippodrome = reunion.get("hippodrome", {}).get("libelleLong", "")

        for course in reunion.get("courses", []):
            num_c = f"C{course.get('numOrdre')}"
            nom_course = course.get("libelle", "")

            url_partants = f"https://online.turfinfo.api.pmu.fr/rest/client/7/programme/{date_pmu}/{num_r}/{num_c}/participants"
            try:
                res_part = requests.get(url_partants, headers=HEADERS, timeout=10)
                chevaux = []
                if res_part.status_code == 200:
                    for p in res_part.json().get("participants", []):
                        deferre_val = p.get("deferre", "")
                        rapport_direct = p.get("dernierRapportDirect")
                        cote_val = rapport_direct.get("rapport") if isinstance(rapport_direct, dict) else None

                        chevaux.append({
                            "num": p.get("numPmu"),
                            "nom": p.get("nom"),
                            "driver": p.get("driver"),
                            "musique": p.get("musique", ""),
                            "deferre": deferre_val,
                            "cote": cote_val,
                        })
                resultats_journee.append({
                    "reunion": num_r,
                    "hippodrome": hippodrome,
                    "course": num_c,
                    "nom_course": nom_course,
                    "chevaux": chevaux,
                })
            except Exception:
                pass

    # Remplacement de l'écriture simple par la fonction de synchronisation
    sauvegarder_et_synchroniser(resultats_journee, fichier_cible, f"Téléchargement courses {date_iso}")
    return True

def charger_donnees_fichier(fichier_json):
    try:
        with open(fichier_json, "r", encoding="utf-8") as f:
            donnees = json.load(f)
        reunions_map = {}
        for elem in donnees:
            cle = f"{elem['reunion']} - {elem['hippodrome']}"
            if cle not in reunions_map:
                reunions_map[cle] = []
            reunions_map[cle].append(elem)
        return donnees, reunions_map
    except Exception:
        return [], {}

def chercher_historique_cheval(nom_cheval, date_actuelle=""):
    historique_cheval = []
    if not nom_cheval:
        return historique_cheval
    
    nom_cheval_upper = nom_cheval.upper().strip()
    fichiers = list(DOSSIER.glob("pmu_du_jour_*.json"))
    
    for f in fichiers:
        date_str = f.stem.replace("pmu_du_jour_", "")
        if date_str == date_actuelle:
            continue
        try:
            with open(f, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
                for reunion in data:
                    for course in reunion.get("courses", []):
                        for cheval in course.get("chevaux", []):
                            if cheval.get("nom", "").upper().strip() == nom_cheval_upper:
                                historique_cheval.append({
                                    "date": date_str,
                                    "hippodrome": reunion.get("hippodrome"),
                                    "course": course.get("nom_course"),
                                    "cote": cheval.get("cote")
                                })
        except Exception:
            continue
    return historique_cheval

def analyser_predictibilite_course(chevaux_valides):
    cotes_triees = sorted([c["cote"] for c in chevaux_valides if isinstance(c.get("cote"), (int, float))])
    if len(cotes_triees) >= 4:
        top4 = cotes_triees[:4]
        if top4[3] - top4[0] < 4.0 and top4[0] > 2.5:
            return True
    return False

def verifier_stop_loss(date_jour):
    if not FICHIER_HISTORIQUE.exists():
        return False
    try:
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
        perte_jour = 0.0
        for p in historique:
            if p.get("date") == date_jour and p.get("statut") != "Annulé":
                mise = float(p.get("mise", 0))
                gain = float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0
                bilan_pari = gain - mise
                if bilan_pari < 0:
                    perte_jour += abs(bilan_pari)
        if perte_jour >= 30.0:
            return True
    except Exception:
        pass
    return False

def evaluer_score_cheval(cheval, date_jour):
    score = 0
    musique = str(cheval.get("musique") or "").upper()
    deferre = str(cheval.get("deferre") or "").upper()
    driver = str(cheval.get("driver") or "").upper()
    cote = cheval.get("cote")
    nom_cheval = cheval.get("nom", "")

    for idx, char in enumerate(musique[:8]):
        if char == "1":
            score += 10 if idx >= 3 else 12
        elif char == "2":
            score += 7
        elif char == "3":
            score += 5
        elif char in ["4", "5"]:
            score += 2
        elif char in ["0", "D", "T", "A"]:
            malus = 6 if (char in ["D", "T", "A"] and idx < 3) else 3
            score -= malus

    if "QUATRE" in deferre:
        score += 8
    elif "ANTERIEURS" in deferre or "POSTERIEURS" in deferre:
        score += 5

    top_drivers = ["BAZIRE", "RAFFIN", "NIVARD", "ABRIVARD", "LAGADEUC", "PLOQUIN", "ROCHARD"]
    if any(td in driver for td in top_drivers):
        score += 6

    if isinstance(cote, (int, float)) and cote > 1.0:
        if cote < 3.0:
            score += 9
        elif 3.0 <= cote <= 6.0:
            score += 7
        elif 6.0 < cote <= 15.0:
            score += 4
        elif cote > 35.0:
            score -= 3

    historique_passe = chercher_historique_cheval(nom_cheval, date_jour)
    if historique_passe:
        score += min(len(historique_passe) * 2, 10)
        cotes_passees = [h["cote"] for h in historique_passe if isinstance(h["cote"], (int, float)) and h["cote"] > 1.0]
        if cotes_passees:
            moyenne_cote = sum(cotes_passees) / len(cotes_passees)
            if moyenne_cote < 8.0:
                score += 5

    return score

# --- INTERFACE STREAMLIT ---

st.title("🐎 Analyse & Stratégie PMU (Web App)")

# Onglets principaux
tab_analyse, tab_suivi = st.tabs(["📊 Analyse & Stratégie", "📈 Suivi & Bilan Financier"])

with tab_analyse:
    col1, col2, col3 = st.columns([2, 2, 2])
    
    with col1:
        date_selectionnee = st.date_input("Date du jour", datetime.date.today())
        date_iso = date_selectionnee.strftime("%Y-%m-%d")
        
    fichier_jour = DOSSIER / f"pmu_du_jour_{date_iso}.json"
    
    with col2:
        if st.button("🔍 Charger / Télécharger les courses"):
            with st.spinner("Téléchargement des données PMU en cours..."):
                succes = telecharger_pmu_date(date_iso, fichier_jour)
                if succes:
                    st.success("Données chargées et synchronisées avec succès !")
                else:
                    st.error("Impossible de récupérer les données pour cette date.")

    if fichier_jour.exists():
        donnees, reunions_map = charger_donnees_fichier(fichier_jour)
        
        liste_reunions = sorted(list(reunions_map.keys()))
        if liste_reunions:
            reunion_choisie = st.selectbox("Réunion", liste_reunions)
            courses_reunion = reunions_map[reunion_choisie]
            
            courses_map = {f"{c['course']} : {c['nom_course']}": c for c in courses_reunion}
            course_choisie_cle = st.selectbox("Course", list(courses_map.keys()))
            course_courante = courses_map[course_choisie_cle]
            
            st.markdown(f"**Hippodrome :** {course_courante['hippodrome']} | **Course :** {course_courante['nom_course']}")
            
            chevaux = course_courante.get("chevaux", [])
            chevaux_valides = [c for c in chevaux if isinstance(c.get("cote"), (int, float)) and c["cote"] > 1.0]
            
            if analyser_predictibilite_course(chevaux_valides):
                st.warning("⚠️ Alerte : Cotes très serrées / Course ouverte (Risque élevé de surprise)")
                
            # Affichage du tableau des partants
            st.subheader("Partants de la course")
            data_tableau = []
            for c in chevaux:
                data_tableau.append({
                    "N°": c.get("num", "-"),
                    "Cheval": c.get("nom", "-"),
                    "Driver / Jockey": c.get("driver", "-"),
                    "Musique": c.get("musique", "-"),
                    "Ferrage": c.get("deferre", "-"),
                    "Cote": f"{c.get('cote'):.1f}" if isinstance(c.get("cote"), (int, float)) else "-"
                })
            st.dataframe(data_tableau, use_container_width=True, hide_index=True)
            
            # Module de paris
            st.divider()
            st.subheader("🧠 Analyse Avancée & Stratégie de Mise")
            
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                mode_jeu = st.selectbox("Type de jeu", ["Automatique", "Simple", "Couplé", "Trio"])
            with col_b2:
                budget = st.number_input("Budget (€)", min_value=1, value=20, step=1)
                
            if st.button("⚡ Lancer l'Analyse"):
                if verifier_stop_loss(date_iso):
                    st.warning("⚠️ Alerte Stop-Loss : Vos pertes cumulées pour cette journée dépassent 30 €.")
                    
                if not chevaux_valides:
                    st.error("Cotes insuffisantes pour lancer l'analyse.")
                else:
                    for c in chevaux_valides:
                        c["score_analyse"] = evaluer_score_cheval(c, date_iso)

                    chevaux_par_score = sorted(chevaux_valides, key=lambda x: x["score_analyse"], reverse=True)
                    
                    if budget >= 2:
                        mise_secu = max(1, int(round(budget * 0.7)))
                        mise_gros = budget - mise_secu
                    else:
                        mise_secu = 1
                        mise_gros = 0

                    favoris_marche = sorted(chevaux_valides, key=lambda x: x["cote"])
                    top_favoris_marche = favoris_marche[:3] if len(favoris_marche) >= 3 else favoris_marche

                    if mode_jeu == "Simple":
                        base_secu = max(top_favoris_marche, key=lambda x: x["score_analyse"]) if top_favoris_marche else chevaux_par_score[0]
                        reste_chevaux = [c for c in chevaux_par_score if c["num"] != base_secu["num"]]
                        coup_poker = reste_chevaux[0] if reste_chevaux else base_secu

                        pari_secu_txt = "Simple Placé (Filet de Sécurité / Remboursement)"
                        pari_gros_txt = "Simple Gagnant (Recherche de Gros Gain)"
                        chevaux_secu_str = f"N°{base_secu['num']} - {base_secu['nom']} (Cote win: {base_secu['cote']:.1f})"
                        chevaux_gros_str = f"N°{coup_poker['num']} - {coup_poker['nom']} (Cote win: {coup_poker['cote']:.1f})"

                    elif mode_jeu == "Couplé":
                        base_secu = max(top_favoris_marche, key=lambda x: x["score_analyse"]) if top_favoris_marche else chevaux_par_score[0]
                        reste_favoris = [c for c in top_favoris_marche if c["num"] != base_secu["num"]]
                        second_secu = reste_favoris[0] if reste_favoris else (chevaux_par_score[1] if len(chevaux_par_score) > 1 else base_secu)
                        outsiders = [c for c in chevaux_valides if 8.0 < c["cote"] <= 30.0 and c["num"] != base_secu["num"]]
                        coup_poker = outsiders[0] if outsiders else (chevaux_par_score[2] if len(chevaux_par_score) > 2 else base_secu)

                        pari_secu_txt = "Couplé Placé (Sécurité Base)"
                        pari_gros_txt = "Couplé Gagnant (Base + Outsider)"
                        chevaux_secu_str = f"N°{base_secu['num']} et N°{second_secu['num']}"
                        chevaux_gros_str = f"N°{base_secu['num']} et N°{coup_poker['num']}"

                    elif mode_jeu == "Trio":
                        c1 = max(top_favoris_marche, key=lambda x: x["score_analyse"]) if top_favoris_marche else chevaux_par_score[0]
                        reste_fav = [c for c in top_favoris_marche if c["num"] != c1["num"]]
                        c2 = reste_fav[0] if reste_fav else (chevaux_par_score[1] if len(chevaux_par_score) > 1 else c1)
                        c3_candidates = [c for c in chevaux_valides if c["num"] not in (c1["num"], c2["num"])]
                        c3 = c3_candidates[0] if c3_candidates else c2
                        outsiders = [c for c in chevaux_valides if 8.0 < c["cote"] and c["num"] not in (c1["num"], c2["num"])]
                        coup_poker = outsiders[0] if outsiders else c3

                        pari_secu_txt = "Trio Ordre / Désordre (Top 3)"
                        pari_gros_txt = "Trio Spéculatif (2 Favoris + 1 Outsider)"
                        chevaux_secu_str = f"N°{c1['num']}, N°{c2['num']}, N°{c3['num']}"
                        chevaux_gros_str = f"N°{c1['num']}, N°{c2['num']}, N°{coup_poker['num']}"
                        base_secu = c1

                    else:
                        base_secu = max(top_favoris_marche, key=lambda x: x["score_analyse"]) if top_favoris_marche else chevaux_par_score[0]
                        outsiders = [c for c in chevaux_valides if 8.0 < c["cote"] <= 30.0 and c["num"] != base_secu["num"]]
                        coup_poker = outsiders[0] if outsiders else (chevaux_par_score[1] if chevaux_par_score[1]["num"] != base_secu["num"] else chevaux_par_score[2])

                        pari_secu_txt = "Simple Placé (Remboursement)"
                        pari_gros_txt = f"Couplé N°{base_secu['num']}-{coup_poker['num']}"
                        chevaux_secu_str = f"N°{base_secu['num']} - {base_secu['nom']} (Cote win: {base_secu['cote']:.1f})"
                        chevaux_gros_str = f"N°{coup_poker['num']} - {coup_poker['nom']} (Cote win: {coup_poker['cote']:.1f})"

                    gain_secu_estime = round(mise_secu * (1.0 + (base_secu["cote"] - 1.0) / 3.0), 2) if mode_jeu == "Simple" else round(mise_secu * base_secu["cote"], 2)
                    gain_gros = round(mise_gros * coup_poker["cote"], 2)

                    col_res1, col_res2 = st.columns(2)
                    with col_res1:
                        st.info(f"🛡️ **Base Sécurité**\n\n**{pari_secu_txt}**\n{chevaux_secu_str}\n👉 Mise : {mise_secu} €\n💰 Remboursement estimé : ~{gain_secu_estime:.2f} €")
                    with col_res2:
                        st.success(f"🚀 **Coup de Poker**\n\n**{pari_gros_txt}**\n{chevaux_gros_str}\n👉 Mise : {mise_gros} €\n🔥 Gain potentiel : {gain_gros:.2f} €")

                    st.session_state["dernier_pari"] = {
                        "date": date_iso,
                        "course": f"{course_courante['reunion']} {course_courante['course']} ({course_courante['hippodrome']})",
                        "type": mode_jeu,
                        "details": f"Sécu: [{chevaux_secu_str}] ({mise_secu}€) | Poker: [{chevaux_gros_str}] ({mise_gros}€)",
                        "mise": budget,
                        "statut": "En attente",
                        "gain": 0.0
                    }

            if "dernier_pari" in st.session_state and st.button("✅ Valider / Enregistrer ce pari"):
                historique = []
                if FICHIER_HISTORIQUE.exists():
                    try:
                        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
                            historique = json.load(f)
                    except Exception:
                        pass
                historique.append(st.session_state["dernier_pari"])
                
                # Sauvegarde et synchronisation automatique sur GitHub
                sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Ajout d'un nouveau pari")
                
                st.success("Pari enregistré et synchronisé avec succès !")
                del st.session_state["dernier_pari"]

with tab_suivi:
    st.subheader("📈 Suivi & Bilan Financier Global")
    
    if FICHIER_HISTORIQUE.exists():
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
            
        total_mise = sum(float(p.get("mise", 0)) for p in historique if p.get("statut") != "Annulé")
        total_gain = sum(float(p.get("gain", 0)) for p in historique if p.get("statut") == "Gagné")
        bilan_net = total_gain - total_mise
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Mise Totale", f"{total_mise:.2f} €")
        col_m2.metric("Gains Totaux", f"{total_gain:.2f} €")
        col_m3.metric("Bilan Net", f"{bilan_net:+.2f} €", delta_color="normal" if bilan_net >= 0 else "inverse")
        
        st.divider()
        st.write("Détail des paris enregistrés :")
        
        data_suivi = []
        for idx, p in enumerate(historique):
            data_suivi.append({
                "Index": idx,
                "Date": p.get("date"),
                "Course": p.get("course"),
                "Type": p.get("type"),
                "Détails": p.get("details"),
                "Mise (€)": p.get("mise"),
                "Statut": p.get("statut"),
                "Gain (€)": p.get("gain", 0.0) if p.get("statut") == "Gagné" else "-"
            })
        st.dataframe(data_suivi, use_container_width=True, hide_index=True)
        
        col_act1, col_act2, col_act3 = st.columns(3)
        with col_act1:
            index_pari = st.number_input("Index du pari à modifier", min_value=0, max_value=max(0, len(historique)-1), step=1)
        with col_act2:
            nouveau_statut = st.selectbox("Nouveau statut", ["En attente", "Gagné", "Perdu", "Annulé"])
        with col_act3:
            gain_saisi = st.number_input("Montant du gain (si Gagné)", min_value=0.0, value=0.0, step=0.5)
            
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Mettre à jour le statut du pari"):
                if 0 <= index_pari < len(historique):
                    historique[index_pari]["statut"] = nouveau_statut
                    historique[index_pari]["gain"] = gain_saisi if nouveau_statut == "Gagné" else 0.0
                    
                    # Sauvegarde et synchronisation automatique sur GitHub après modification
                    sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Mise à jour statut pari")
                    
                    st.success("Mise à jour et synchronisation effectuées !")
                    st.rerun()
                    
        with col_btn2:
            if st.button("🗑️ Supprimer ce pari"):
                if 0 <= index_pari < len(historique):
                    pari_supprime = historique.pop(index_pari)
                    
                    # Sauvegarde et synchronisation automatique sur GitHub après suppression
                    sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, f"Suppression du pari index {index_pari}")
                    
                    st.success("Pari supprimé et synchronisé avec succès !")
                    st.rerun()
    else:
        st.info("Aucun historique de pari enregistré pour le moment.")
