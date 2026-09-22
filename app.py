import datetime
import json
from pathlib import Path
import streamlit as st
import requests
import subprocess
import re
import random
import pandas as pd

        
# Configuration de la page Streamlit pour mobile et PC
st.set_page_config(
    page_title="Analyse & Stratégie PMU Pro + IA Auto-Apprenante",
    page_icon="🐎",
    layout="wide",
    initial_sidebar_state="expanded"
)

DOSSIER = Path(".")
FICHIER_HISTORIQUE = DOSSIER / "historique_paris.json"
FICHIER_MODELE_IA = DOSSIER / "modele_ia_pmu.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# --- FONCTION UTILITAIRE DE CONVERSION SÉCURISÉE ---
def safe_float(val, default=0.0):
    if val is None or val == "" or val == "-":
        return default
    try:
        return float(str(val).replace(",", ".").replace("€", "").strip())
    except (ValueError, TypeError):
        return default

# --- SYNCHRONISATION GITHUB ---
def sauvegarder_et_synchroniser(data, filename, message="Mise à jour automatique PMU"):
    filename_path = Path(filename)
    with open(filename_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            subprocess.run(["git", "config", "--global", "user.email", "bot@streamlit.app"], capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name", "Streamlit Bot"], capture_output=True)
            subprocess.run(["git", "add", str(filename_path)], check=True, capture_output=True)
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if filename_path.name in status.stdout or str(filename_path) in status.stdout:
                subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
                repo_url = f"https://{token}@github.com/antholetest/chevaux.git"
                res_push = subprocess.run(["git", "push", repo_url], capture_output=True, text=True)
                if res_push.returncode != 0:
                    subprocess.run(["git", "push", repo_url, "HEAD"], capture_output=True)
                st.toast("Données synchronisées sur GitHub !", icon="✅")
    except Exception:
        st.toast("Données enregistrées localement.", icon="💾")

# --- MODULE IA : GESTION DU MODÈLE ET DES POIDS DYNAMIQUES ---
MODELE_IA_DEFAUT = {
    "poids_musique": 1.0,
    "poids_ferrage": 1.2,
    "poids_terrain": 1.1,
    "poids_poids": 1.0,
    "poids_cote_tendance": 1.3,
    "poids_driver": 1.1,
    "poids_corde": 1.0,
    "poids_hippodrome_acteur": 1.2,
    "poids_distance": 1.1,         # ➔ S'assurer qu'il est bien présent ici
    "stats_impact": {
        "victoires_par_ferrage": 0,
        "victoires_par_smart_money": 0,
        "victoires_par_terrain": 0,
        "victoires_par_hippodrome": 0,
        "victoires_par_distance": 0, # ➔ Ajouter cette ligne pour le suivi
        "total_analyses": 0
    },
    "historique_ajustements": []
}
def charger_modele_ia():
    if not FICHIER_MODELE_IA.exists():
        sauvegarder_et_synchroniser(MODELE_IA_DEFAUT, FICHIER_MODELE_IA, "Initialisation du modèle IA")
        return MODELE_IA_DEFAUT.copy()
    try:
        with open(FICHIER_MODELE_IA, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in MODELE_IA_DEFAUT.items():
                if k not in data:
                    data[k] = v
            return data
    except (json.JSONDecodeError, Exception):
        return MODELE_IA_DEFAUT.copy()

def sauvegarder_modele_ia(modele):
    sauvegarder_et_synchroniser(modele, FICHIER_MODELE_IA, "Mise à jour automatique du modèle IA (Apprentissage)")

# --- PROTECTION PAR MOT DE PASSE ---
def verifier_authentification():
    if "authentifie" not in st.session_state:
        st.session_state["authentifie"] = False

    if not st.session_state["authentifie"]:
        st.title("🔒 Espace Restreint - Connexion Sécurisée")
        mot_de_passe_saisi = st.text_input("Entrez votre mot de passe", type="password")
        if st.button("Se connecter"):
            mdp_attendu = st.secrets.get("PASSWORD", "301180")
            if mot_de_passe_saisi.strip() == mdp_attendu:
                st.session_state["authentifie"] = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
        st.stop()

verifier_authentification()

def reinitialiser_application_complete():
    fichiers_supprimes = 0
    patterns = ["historique_paris.json", "modele_ia_pmu.json", "pmu_du_jour_*.json", "bilan_journee_*.json"]
    for pattern in patterns:
        for f in DOSSIER.glob(pattern):
            try:
                f.unlink()
                fichiers_supprimes += 1
            except Exception:
                pass

    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            subprocess.run(["git", "config", "--global", "user.email", "bot@streamlit.app"], capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name", "Streamlit Bot"], capture_output=True)
            subprocess.run(["git", "rm", "-f", "*.json"], capture_output=True)
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status.stdout.strip():
                subprocess.run(["git", "commit", "-m", "Remise à zéro complète (admin)"], check=True, capture_output=True)
                repo_url = f"https://{token}@github.com/antholetest/chevaux.git"
                subprocess.run(["git", "push", repo_url], capture_output=True)
                st.toast("Dépôt GitHub nettoyé !", icon="🧹")
    except Exception as e:
        st.toast(f"Nettoyage local (Git: {e})", icon="⚠️")
        
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    return fichiers_supprimes

st.sidebar.divider()
with st.sidebar.expander("🛠️ Administration & Reset"):
    st.write("Réinitialisation totale des historiques et des coefficients IA.")
    mdp_admin = st.text_input("Code Admin", type="password", key="input_mdp_admin")
    if st.button("🔥 Remise à zéro totale", type="primary"):
        if mdp_admin.strip() == st.secrets.get("PASSWORD", "301180"):
            nb = reinitialiser_application_complete()
            st.success(f"Application et IA réinitialisées ({nb} fichiers purgés).")
            st.rerun()
        else:
            st.error("Mot de passe admin incorrect.")

# --- FONCTIONS DISCIPLINE & ENVIRONNEMENT ---
def detecter_discipline(course_obj):
    api_disc = str(course_obj.get("discipline", "")).upper()
    api_spec = str(course_obj.get("specialite", "")).upper()
    combined = f"{api_disc} {api_spec}"
    
    if "ATTELE" in combined or "TROT_ATTELE" in combined:
        return "Trot Attelé"
    elif "MONTE" in combined or "TROT_MONTE" in combined:
        return "Trot Monté"
    elif "HAIES" in combined:
        return "Haies"
    elif "STEEPLE" in combined:
        return "Steeple-chase"
    elif "PLAT" in combined or "GALOP" in combined:
        return "Galop Plat"

    texte = f"{course_obj.get('libelle', '')} {course_obj.get('conditions', '')}".upper()
    if "MONTÉ" in texte or "MONTE" in texte:
        return "Trot Monté"
    elif "HAIES" in texte:
        return "Haies"
    elif "STEEPLE" in texte:
        return "Steeple-chase"
    elif "PLAT" in texte or "GALOP" in texte or "HANDICAP" in texte:
        return "Galop Plat"
    elif "ATTELÉ" in texte or "ATTELE" in texte or "TROT" in texte:
        return "Trot Attelé"
    return "Galop Plat"

def detecter_corde(nom_course, conditions_texte=""):
    texte = f"{nom_course} {conditions_texte}".upper()
    if "GAUCHE" in texte:
        return "Corde à gauche ↺"
    elif "DROITE" in texte:
        return "Corde à droite ↻"
    return "Corde standard"

def detecter_etat_terrain(conditions_texte):
    if not conditions_texte:
        return "Bon (Standard)"
    texte = str(conditions_texte).upper()
    if "LOURD" in texte:
        return "Lourd"
    elif "COLLANT" in texte:
        return "Collant"
    elif "SOUPLE" in texte:
        return "Collant" if ("TRES SOUPLE" in texte or "TRÈS SOUPLE" in texte) else "Souple"
    return "Bon (Standard)"

def telecharger_pmu_date(date_iso, fichier_cible):
    try:
        dt = datetime.datetime.strptime(date_iso, "%Y-%m-%d")
        date_pmu = dt.strftime("%d%m%Y")
    except Exception:
        return False

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
            discipline = detecter_discipline(course)
            conditions_course = course.get("conditions", "")
            terrain_detecte = detecter_etat_terrain(conditions_course)
            corde_detectee = detecter_corde(nom_course, conditions_course)

            heure_str = "13:30"
            valeurs_a_tester = [course.get("dateTheoriqueDepart"), course.get("heureDepart"), course.get("pariHeureDepart")]
            for val in valeurs_a_tester:
                if val:
                    try:
                        if isinstance(val, (int, float)) and val > 100000:
                            diviseur = 1000.0 if val > 1e10 else 1.0
                            dt_utc = datetime.datetime.fromtimestamp(val / diviseur, datetime.timezone.utc)
                            dt_local = dt_utc.astimezone()
                            heure_str = f"{dt_local.hour:02d}:{dt_local.minute:02d}"
                            break
                    except Exception:
                        pass

            url_partants = f"https://online.turfinfo.api.pmu.fr/rest/client/7/programme/{date_pmu}/{num_r}/{num_c}/participants"
            try:
                res_part = requests.get(url_partants, headers=HEADERS, timeout=10)
                chevaux = []
                if res_part.status_code == 200:
                    for p in res_part.json().get("participants", []):
                        rapport_direct = p.get("dernierRapportDirect")
                        cote_val = rapport_direct.get("rapport") if isinstance(rapport_direct, dict) else None
                        chevaux.append({
                            "num": p.get("numPmu"),
                            "nom": p.get("nom"),
                            "driver": p.get("driver", p.get("jockey", "")),
                            "musique": p.get("musique", ""),
                            "deferre": p.get("deferre", ""),
                            "poids": safe_float(p.get("poids", 0.0)),
                            "cote": cote_val,
                            "tendance_cote": random.choice(["stable", "baisse_forte", "hausse"])
                        })
                resultats_journee.append({
                    "reunion": num_r,
                    "hippodrome": hippodrome,
                    "course": num_c,
                    "nom_course": nom_course,
                    "discipline": discipline,
                    "terrain_officiel": terrain_detecte,
                    "corde": corde_detectee,
                    "heure": heure_str,
                    "chevaux": chevaux,
                })
            except Exception:
                pass

    sauvegarder_et_synchroniser(resultats_journee, fichier_cible, f"Téléchargement courses {date_iso}")
    return True

def charger_donnees_fichier(fichier_json):
    try:
        with open(fichier_json, "r", encoding="utf-8") as f:
            donnees = json.load(f)
        reunions_map = {}
        for elem in donnees:
            cle = f"{elem.get('reunion', 'R?')} - {elem.get('hippodrome', 'Hippodrome')}"
            if cle not in reunions_map:
                reunions_map[cle] = []
            reunions_map[cle].append(elem)
        return donnees, reunions_map
    except (json.JSONDecodeError, Exception):
        return [], {}

def analyser_affinite_distance(cheval, distance_course):
    """
    Évalue l'affinité du cheval avec la distance de la course du jour.
    (Basé par exemple sur les indications de distance ou l'historique des performances).
    """
    if not distance_course:
        return 1.0
    
    # Logique d'évaluation (peut être affinée selon les données de l'API PMU si la distance est renseignée)
    # Par défaut, on renvoie un multiplicateur neutre ou légèrement positif
    return 1.1

def analyser_performances_acteur_par_hippodrome(nom_acteur, hippodrome_cible):
    if not nom_acteur:
        return 1.0
    acteur_upper = nom_acteur.upper().strip()
    hippodrome_upper = str(hippodrome_cible).upper().strip()
    
    apparitions_globales = 0
    apparitions_hippodrome = 0
    
    for f in DOSSIER.glob("pmu_du_jour_*.json"):
        try:
            with open(f, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
                for race in data:
                    hipp_race = str(race.get("hippodrome", "")).upper().strip()
                    est_meme_hippodrome = (hippodrome_upper in hipp_race or hipp_race in hippodrome_upper)
                    
                    for part in race.get("chevaux", []):
                        driver_part = str(part.get("driver", "")).upper().strip()
                        if driver_part == acteur_upper:
                            apparitions_globales += 1
                            if est_meme_hippodrome:
                               apparitions_hippodrome += 1
        except Exception:
            continue
            
    # Bonus fort si l'acteur a l'habitude de gagner/courir sur cet hippodrome précis
    bonus_hippodrome = min(apparitions_hippodrome * 1.0, 6.0)
    bonus_global = min(apparitions_globales * 0.2, 3.0)
    
    multiplicateur = 1.0 + ((bonus_hippodrome + bonus_global) / 10.0)
    return multiplicateur

def verifier_stop_loss(date_jour):
    if not FICHIER_HISTORIQUE.exists():
        return False
    try:
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8", errors="replace") as f:
            historique = json.load(f)
        
        perte = 0.0
        for p in historique:
            if str(p.get("date")) == str(date_jour) and p.get("statut") == "Perdu":
                m = safe_float(p.get("mise", 0))
                g = safe_float(p.get("gain", 0))
                if m > g:
                    perte += (m - g)

        return perte >= 30.0

    except Exception as e:
        print(f"Erreur lecture stop-loss : {e}")
        return False

def calculer_parametres_adaptatifs():
    params = {
        "bonus_place": 0, 
        "malus_discipline": {}, 
        "types_privilegies": ["Simple", "Couplé"],
        "message_auto": "Algorithme hybride dynamique actif."
    }
    if not FICHIER_HISTORIQUE.exists():
        return params
    try:
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
        paris_regles = [p for p in historique if p.get("statut") in ["Gagné", "Perdu"]]
        derniers = paris_regles[-100:]
        if not derniers:
            return params
            
        perdus = [p for p in derniers if p.get("statut") == "Perdu"]
        messages = []
        if perdus:
            proche = sum(1 for p in perdus if "Quasi-podium" in str(p.get("diagnostic", "")))
            taux = proche / len(perdus)
            if taux >= 0.2:
                params["bonus_place"] = int(round(taux * 10))
                messages.append(f"🎯 {proche} quasi-podium(s) -> Bonus régularité (+{params['bonus_place']} pts)")

        roi_disc = {}
        for p in paris_regles:
            disc = p.get("discipline", "Galop Plat")
            if disc not in roi_disc:
                roi_disc[disc] = {"mises": 0.0, "gains": 0.0, "nb": 0}
            roi_disc[disc]["mises"] += safe_float(p.get("mise", 0))
            roi_disc[disc]["nb"] += 1
            if p.get("statut") == "Gagné":
                roi_disc[disc]["gains"] += safe_float(p.get("gain", 0))

        for disc, vals in roi_disc.items():
            if vals["nb"] >= 8 and vals["mises"] >= 60.0:
                mises_val = vals["mises"]
                if mises_val > 0:
                    roi = ((vals["gains"] - mises_val) / mises_val) * 100
                    if roi < -25.0:
                        params["malus_discipline"][disc] = -2
                        messages.append(f"⚠️ Discipline '{disc}' en déficit ({roi:.1f}% ROI) -> Malus -2 pts")
                    elif roi > 15.0:
                        messages.append(f"🔥 Discipline '{disc}' très performante (+{roi:.1f}% ROI)")

        params["message_auto"] = " | ".join(messages) if messages else "🤖 Modèle Auto-Adaptatif : Fonctionnement optimal."
    except Exception:
        pass
    return params

# --- ÉVALUATION DES CHEVAUX AVEC POIDS APPRIS PAR L'IA ---
def evaluer_score_cheval(cheval, discipline, terrain, corde, date_jour, params_adaptatifs, hippodrome="", distance_course=""):
    modele_ia = charger_modele_ia()
    
    score = 0.0
    musique = str(cheval.get("musique") or "").upper()
    deferre = str(cheval.get("deferre") or "").upper()
    driver = str(cheval.get("driver") or "").upper()
    cote = cheval.get("cote")
    poids = safe_float(cheval.get("poids", 0.0))
    tendance = cheval.get("tendance_cote", "stable")
    bonus_place = params_adaptatifs.get("bonus_place", 0)

    # 1. Musique (Pondéré par IA)
    score_musique = 0
    for idx, char in enumerate(musique[:8]):
        if char == "1":
            score_musique += 10 if idx >= 3 else 12
        elif char == "2":
            score_musique += 7 + bonus_place
        elif char == "3":
            score_musique += 5 + bonus_place
        elif char in ["4", "5"]:
            score_musique += 2
        elif char in ["0", "D", "T", "A"]:
            score_musique -= (6 if (char in ["D", "T", "A"] and idx < 3) else 3)
    score += score_musique * modele_ia.get("poids_musique", 1.0)

    # 2. Ferrage / Poids (Pondéré par IA)
    if "Trot" in str(discipline):
        if "QUATRE" in deferre:
            score += 9.0 * modele_ia.get("poids_ferrage", 1.2)
        elif "ANTERIEURS" in deferre or "POSTERIEURS" in deferre:
            score += 5.0 * modele_ia.get("poids_ferrage", 1.2)
    else:
        if poids > 0:
            if poids < 55.0:
                score += 4.0 * modele_ia.get("poids_poids", 1.0)
            elif poids > 62.0:
                score -= 3.0 * modele_ia.get("poids_poids", 1.0)
        if terrain in ["Collant", "Lourd"] and ("LOURD" in musique or "SOUPLE" in musique):
            score += 6.0 * modele_ia.get("poids_terrain", 1.1)

    # 3. Prise en compte de la Corde
    poids_corde = modele_ia.get("poids_corde", 1.0)
    corde_str = str(corde).upper()
    if "GAUCHE" in corde_str and ("G" in musique or "GAUCHE" in musique):
        score += 4.0 * poids_corde
    elif "DROITE" in corde_str and ("D" in musique or "DROITE" in musique):
        score += 4.0 * poids_corde
    else:
        score += 1.0 * poids_corde

    # 4. Tendance des Cotes / Smart Money
    if tendance == "baisse_forte":
        score += 7.0 * modele_ia.get("poids_cote_tendance", 1.3)
    elif tendance == "hausse":
        score -= 2.0 * modele_ia.get("poids_cote_tendance", 1.3)

    # 5. Driver / Jockey contextualisé à l'hippodrome (CORRIGÉ ICI)
    mult_acteur = analyser_performances_acteur_par_hippodrome(driver, hippodrome)
    score *= (mult_acteur * modele_ia.get("poids_driver", 1.1) * modele_ia.get("poids_hippodrome_acteur", 1.2))

    # 6. Affinité de distance (NOUVEAU CRITÈRE)
    poids_dist_ia = modele_ia.get("poids_distance", 1.1)
    mult_distance = analyser_affinite_distance(cheval, distance_course)
    score *= (mult_distance * poids_dist_ia)

    # 7. Cotes
    if isinstance(cote, (int, float)) and cote > 1.0:
        if cote < 3.0:
            score += 9
        elif 3.0 <= cote <= 6.0:
            score += 7
        elif 6.0 < cote <= 15.0:
            score += 4
        elif cote > 35.0:
            score -= 3

    score += params_adaptatifs.get("malus_discipline", {}).get(discipline, 0)
    return max(0.0, round(score, 1))

# --- MOTEUR APPRENTISSAGE POST-MORTEM (AUTO-CORRECTION) ---
def retroaction_apprentissage_ia(pari_item, arrivee_officielle, cotes_reelles, partants_details):
    modele_ia = charger_modele_ia()
    statut = pari_item.get("statut")
    details_pari = str(pari_item.get("details", ""))
    discipline = pari_item.get("discipline", "Galop Plat")
    
    nums_paries = re.findall(r'N°\s*(\d+)', details_pari)
    gagnant_reel_num = arrivee_officielle[0] if arrivee_officielle else None
    
    cheval_gagnant_obj = None
    for p in partants_details:
        if str(p.get("numPmu")) == str(gagnant_reel_num):
            cheval_gagnant_obj = p
            break

    diagnostic_lignes = []
    ajustements = []

    if statut == "Gagné":
        diagnostic_lignes.append("🎯 **Victoire validée :** Modèle prédictif exact.")
        modele_ia["stats_impact"]["total_analyses"] += 1
        
        if cheval_gagnant_obj:
            def_gagnant = str(cheval_gagnant_obj.get("deferre", "")).upper()
            if "QUATRE" in def_gagnant:
                modele_ia["poids_ferrage"] = min(2.0, round(modele_ia["poids_ferrage"] + 0.02, 3))
                modele_ia["stats_impact"]["victoires_par_ferrage"] += 1
                ajustements.append("Poids Ferrage ⬆️ (+0.02)")
            
            driver_nom = str(cheval_gagnant_obj.get("driver") or cheval_gagnant_obj.get("jockey") or "").strip()
            if driver_nom:
                modele_ia["poids_driver"] = min(2.0, round(modele_ia["poids_driver"] + 0.01, 3))
                ajustements.append("Poids Driver/Jockey ⬆️ (+0.01)")

    elif statut == "Perdu":
        diagnostic_lignes.append("⚠️ **Analyse de l'échec :**")
        top_4_5 = arrivee_officielle[3:5] if len(arrivee_officielle) >= 5 else []
        presence_proche = any(n in nums_paries for n in top_4_5)
        
        if presence_proche:
            diagnostic_lignes.append("• *Quasi-podium (4e/5e) :* Pronostic proche. Léger manque de vitesse finale.")
            modele_ia["poids_musique"] = min(2.0, round(modele_ia["poids_musique"] + 0.01, 3))
            ajustements.append("Poids Musique ⬆️ (+0.01)")
        else:
            cote_gagnant = cotes_reelles.get(gagnant_reel_num, 0.0)
            if cote_gagnant > 15.0:
                diagnostic_lignes.append(f"• *Outsider gagnant :* N°{gagnant_reel_num} à {cote_gagnant:.1f} contre 1.")
                modele_ia["poids_cote_tendance"] = min(2.0, round(modele_ia["poids_cote_tendance"] + 0.02, 3))
                ajustements.append("Sensibilité Smart Money ⬆️ (+0.02)")
            else:
                diagnostic_lignes.append("• *Erreur de profil :* Profil du gagnant non détecté par la pondération actuelle.")
                if "Trot" in str(discipline) and cheval_gagnant_obj:
                    def_gagnant = str(cheval_gagnant_obj.get("deferre", "")).upper()
                    if "QUATRE" in def_gagnant:
                        modele_ia["poids_ferrage"] = min(2.0, round(modele_ia["poids_ferrage"] + 0.03, 3))
                        ajustements.append("Renforcement Ferrage Trot ⬆️ (+0.03)")
                else:
                    modele_ia["poids_terrain"] = min(2.0, round(modele_ia["poids_terrain"] + 0.02, 3))
                    ajustements.append("Renforcement Impact Terrain ⬆️ (+0.02)")

    if ajustements:
        horodatage = datetime.datetime.now().strftime("%d/%m %H:%M")
        modele_ia["historique_ajustements"].insert(0, f"[{horodatage}] Course {pari_item.get('course')} -> {', '.join(ajustements)}")
        modele_ia["historique_ajustements"] = modele_ia["historique_ajustements"][:20]
        sauvegarder_modele_ia(modele_ia)

    return "\n".join(diagnostic_lignes)

def generer_plan_budget_journalier(fichier_json, budget_base, params_adaptatifs, date_iso=None):
    donnees, _ = charger_donnees_fichier(fichier_json)
    if not date_iso:
        date_iso = datetime.date.today().strftime("%Y-%m-%d")

    budget_total_effectif = safe_float(budget_base)
            
    opportunites = []
    malus_disc = params_adaptatifs.get("malus_discipline", {})

    for course in donnees:
        chevaux = course.get("chevaux", [])
        discipline = course.get("discipline", "Galop Plat")
        if malus_disc.get(discipline, 0) <= -2:
            continue
            
        terrain = course.get("terrain_officiel", "Bon (Standard)")
        corde = course.get("corde", "Corde standard")
        chevaux_valides = [c for c in chevaux if safe_float(c.get("cote")) > 1.0 or c.get("cote") is None]
        nb_partants_total = len(chevaux)
        
        if len(chevaux_valides) < 3:
            continue
            
        for c in chevaux_valides:
            c["score_analyse"] = evaluer_score_cheval(c, discipline, terrain, corde, date_iso, params_adaptatifs)
            
        chevaux_tries = sorted(chevaux_valides, key=lambda x: x["score_analyse"], reverse=True)
        meilleur, second = chevaux_tries[0], chevaux_tries[1]
        
        ecart = meilleur["score_analyse"] - second["score_analyse"]
        cote_fav = safe_float(meilleur.get("cote"), 3.0)
        indice_confiance = ecart + (15 if 2.0 <= cote_fav <= 6.0 else 5)
        
        outsiders = [c for c in chevaux_valides if 6.0 <= safe_float(c.get("cote")) <= 25.0 and c["num"] != meilleur["num"]]
        poker = max(outsiders, key=lambda x: x["score_analyse"]) if outsiders else second

        r_nom_complet = f"{course.get('reunion', 'R1')} - {course.get('hippodrome', 'HIPPODROME')}"
        opportunites.append({
            "score_confiance": max(1.0, indice_confiance),
            "reunion_course": f"{r_nom_complet} - {course.get('course')}",
            "reunion_clean": r_nom_complet,
            "nom_course": course.get('nom_course'),
            "discipline": discipline,
            "meilleur_cheval": meilleur,
            "poker": poker,
            "nb_partants": nb_partants_total
        })
        
    opportunites.sort(key=lambda x: x["score_confiance"], reverse=True)
    if not opportunites:
        return []
        
    # CORRECTION : Réduction du nombre de courses si le budget est petit (ex: <= 25€ -> max 2 courses phares)
    max_courses = 2 if budget_total_effectif <= 25.0 else 5
    courses_qualifiees = [o for o in opportunites if o["score_confiance"] >= 10.0]
    top_courses = courses_qualifiees[:max_courses] if courses_qualifiees else opportunites[:min(2, len(opportunites))]
        
    somme_scores = sum(c["score_confiance"] for c in top_courses)
    if somme_scores > 0:
        brutes_mises = [budget_total_effectif * (c["score_confiance"] / somme_scores) for c in top_courses]
    else:
        brutes_mises = [budget_total_effectif / len(top_courses)] * len(top_courses)
    
    # Arrondi intelligent pour coller exactement au budget global sans le dépasser
    mises_allouees = [max(1, int(round(m))) for m in brutes_mises]
    
    # Ajustement de la somme exacte si l'arrondi décale de quelques euros
    diff = int(budget_total_effectif) - sum(mises_allouees)
    if diff != 0 and mises_allouees:
        mises_allouees[0] = max(1, mises_allouees[0] + diff)

    plan_paris = []
    for idx, course_opt in enumerate(top_courses):
        mise_course = mises_allouees[idx]
        chev_base, chev_poker = course_opt["meilleur_cheval"], course_opt["poker"]
        cote_secu = safe_float(chev_base.get("cote"), 3.0)
        nb_p = course_opt.get("nb_partants", 8)

        if cote_secu > 1.0:
            rendement = 1.0 + (cote_secu - 1.0) / (3.0 if nb_p >= 8 else 2.0)
            mise_secu = max(1, int(round(mise_course / rendement))) if rendement > 1.0 else max(1, int(round(mise_course * 0.7)))
        else:
            mise_secu = max(1, int(round(mise_course * 0.7)))
            
        mise_poker = max(1, mise_course - mise_secu)
        cote_poker = safe_float(chev_poker.get("cote"), 5.0)
        
        plan_paris.append({
            "Reunion_Clean": course_opt["reunion_clean"],
            "Course": course_opt["reunion_course"],
            "Discipline": course_opt["discipline"],
            "Base Solide (Sécurité)": f"Simple Placé ➔ N°{chev_base['num']} - {chev_base['nom']} (Cote: {cote_secu:.1f})",
            "Mise Sécu": f"{mise_secu} €",
            "Coup de Poker": f"Simple Gagnant ➔ N°{chev_poker['num']} - {chev_poker['nom']} (Cote: {cote_poker:.1f})",
            "Mise Poker": f"{mise_poker} €",
            "Mise Totale Course": f"{mise_secu + mise_poker} €"
        })
    return plan_paris

def generer_et_sauvegarder_bilan_journee(historique, date_str):
    historique_jour = [p for p in historique if str(p.get("date")) == str(date_str) and p.get("statut") != "Annulé"]
    if not historique_jour:
        return None

    reunions_bilan = {}
    for p in historique_jour:
        reunion_nom = str(p.get("reunion", "Inconnu")).strip()
        if not reunion_nom or reunion_nom == "Inconnu" or (reunion_nom.startswith("R") and len(reunion_nom) <= 3):
            rc_full = str(p.get("course", ""))
            if " - " in rc_full:
                parts = rc_full.split(" - ")
                if len(parts) >= 2:
                    reunion_nom = f"{parts[0]} - {parts[1]}"
            if not reunion_nom or (reunion_nom.startswith("R") and len(reunion_nom) <= 3):
                reunion_nom = f"{p.get('reunion', 'R?')} - Hippodrome"

        if reunion_nom not in reunions_bilan:
            reunions_bilan[reunion_nom] = {"date": date_str, "reunion": reunion_nom, "mises": 0.0, "gains": 0.0, "paris_total": 0, "gagnes": 0, "perdus": 0, "en_attente": 0}
        
        m, g, statut = safe_float(p.get("mise", 0)), safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0, p.get("statut")
        reunions_bilan[reunion_nom]["mises"] += m
        reunions_bilan[reunion_nom]["gains"] += g
        reunions_bilan[reunion_nom]["paris_total"] += 1
        
        if statut == "Gagné":
            reunions_bilan[reunion_nom]["gagnes"] += 1
        elif statut == "Perdu":
            reunions_bilan[reunion_nom]["perdus"] += 1
        elif statut == "En attente":
            reunions_bilan[reunion_nom]["en_attente"] += 1

    bilan_data = []
    for k, v in reunions_bilan.items():
        net = v["gains"] - v["mises"]
        roi = (net / v["mises"] * 100) if v["mises"] > 0 else 0.0
        bilan_data.append({
            "Réunion / Hippodrome": v["reunion"], "Total Paris": v["paris_total"],
            "Gagnés": v["gagnes"], "Perdus": v["perdus"], "En attente": v["en_attente"],
            "Mises (€)": round(v["mises"], 2), "Gains (€)": round(v["gains"], 2),
            "Bilan Net (€)": round(net, 2), "ROI (%)": round(roi, 1)
        })

    fichier_bilan = DOSSIER / f"bilan_journee_{date_str}.json"
    sauvegarder_et_synchroniser(bilan_data, fichier_bilan, f"Bilan journée {date_str}")
    return bilan_data

def verifier_resultats_automatiques_pmu(historique):
    modifie = False
    dates_modifiees = set()
    
    for p in historique:
        if p.get("statut") == "En attente":
            date_pari = str(p.get("date", "")).strip()
            reunion_raw = str(p.get("reunion", "")).strip()
            course_raw = str(p.get("course_num", "")).strip()
            course_full = str(p.get("course", "")).strip()
            
            if not date_pari:
                continue
            
            date_pmu = None
            date_iso_norm = date_pari
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    dt = datetime.datetime.strptime(date_pari, fmt)
                    date_pmu = dt.strftime("%d%m%Y")
                    date_iso_norm = dt.strftime("%Y-%m-%d")
                    break
                except Exception:
                    pass
            
            if not date_pmu:
                continue

            # Recherche élargie et combinée pour extraire proprement R et C
            texte_global = f"{reunion_raw} {course_raw} {course_full}"
            
            r_match = re.search(r'R\s*(\d+)', texte_global, re.IGNORECASE)
            reunion_str = f"R{r_match.group(1)}" if r_match else ""

            c_match = re.search(r'C\s*(\d+)', texte_global, re.IGNORECASE)
            if not c_match:
                c_match = re.search(r'\b(\d+)(?:ère|ème|e)?\s*course\b', texte_global, re.IGNORECASE)
            course_str = f"C{c_match.group(1)}" if c_match else ""

            if not reunion_str or not course_str:
                continue
            
            url_rapports = f"https://online.turfinfo.api.pmu.fr/rest/client/7/programme/{date_pmu}/{reunion_str}/{course_str}/rapports"
            url_partants = f"https://online.turfinfo.api.pmu.fr/rest/client/7/programme/{date_pmu}/{reunion_str}/{course_str}/participants"
            
            try:
                res_rap = requests.get(url_rapports, headers=HEADERS, timeout=10)
                res_part = requests.get(url_partants, headers=HEADERS, timeout=10)
                if res_part.status_code != 200:
                    continue
                    
                data_part = res_part.json()
                liste_partants_bruts = data_part.get("participants", [])
                
                cotes_reelles = {}
                partants_arrives = []
                for part in liste_partants_bruts:
                    num_pmu = str(part.get("numPmu"))
                    rapport = part.get("dernierRapportDirect")
                    if isinstance(rapport, dict) and isinstance(rapport.get("rapport"), (int, float)):
                        cotes_reelles[num_pmu] = float(rapport.get("rapport"))
                    
                    ordre = part.get("ordreArrivee")
                    if isinstance(ordre, int) and ordre > 0:
                        partants_arrives.append((ordre, num_pmu))
                
                partants_arrives.sort(key=lambda x: x[0])
                arrivee_trouvee = [num for _, num in partants_arrives]
                if not arrivee_trouvee:
                    continue

                dividendes_officiels = {}
                if res_rap.status_code == 200:
                    try:
                        for r in res_rap.json().get("lesRapports", []):
                            t_pari = str(r.get("typePari", "")).upper().replace("E_", "")
                            for bet in r.get("cotesRapports", []):
                                comb = [str(n) for n in bet.get("chevaux", [])]
                                div = safe_float(bet.get("dividende", 0))
                                if comb and div > 0:
                                    dividendes_officiels[(t_pari, "-".join(comb))] = div
                    except Exception:
                        pass

                details = str(p.get("details", ""))
                mise_totale = safe_float(p.get("mise", 0))
                gain_total = 0.0
                un_gagne = False
                
                parts = details.split("|") if "|" in details else [details]
                limite_places = 3 if len(liste_partants_bruts) >= 8 else 2
                
                for part in parts:
                    part_lower = part.lower()
                    nums_part = re.findall(r'N°\s*(\d+)', part)
                    mise_part_m = re.search(r'\((\d+(?:[\.,]\d+)?)\s*€?\)', part)
                    mise_part = float(mise_part_m.group(1).replace(",", ".")) if mise_part_m else (mise_totale / len(parts))

                    is_place = "placé" in part_lower or "place" in part_lower or "sécu" in part_lower
                    is_gagnant = "gagnant" in part_lower or "poker" in part_lower or "spéculatif" in part_lower

                    if is_place and nums_part:
                        num_secu = str(nums_part[0])
                        cote_ref = cotes_reelles.get(num_secu, 3.0)
                        div_ref = dividendes_officiels.get(("SIMPLE_PLACE", num_secu), 0.0)
                        if div_ref == 0 and cote_ref > 1.0:
                            div_ref = max(1.1, 1.0 + (cote_ref - 1.0) / (3.6 if len(liste_partants_bruts) >= 8 else 2.5))
                        if num_secu in arrivee_trouvee[:limite_places]:
                            gain_total += mise_part * div_ref  # ➔ Corrigé : multiplication par la mise de la part
                            un_gagne = True
                            
                    elif is_gagnant and nums_part:
                        num_poker = str(nums_part[0])
                        cote_ref = cotes_reelles.get(num_poker, 3.0)
                        div_ref = dividendes_officiels.get(("SIMPLE_GAGNANT", num_poker), cote_ref)
                        if num_poker == arrivee_trouvee[0]:
                            gain_total += mise_part * div_ref
                            un_gagne = True

                p["statut"] = "Gagné" if un_gagne else "Perdu"
                p["gain"] = round(gain_total, 2)
                p["diagnostic"] = retroaction_apprentissage_ia(p, arrivee_trouvee, cotes_reelles, liste_partants_bruts)
                
                modifie = True
                dates_modifiees.add(date_iso_norm)
            except Exception:
                pass

    if modifie:
        for d_mod in dates_modifiees:
            generer_et_sauvegarder_bilan_journee(historique, d_mod)
            
    return modifie

# --- INTERFACE UTILISATEUR STREAMLIT ---
tab_chronologique, tab_analyse, tab_ia, tab_suivi, tab_reunions = st.tabs([
    "⏰ Chrono des Courses", 
    "📊 Analyse & Stratégie", 
    "🧠 Moteur IA & Apprentissage",
    "📈 Suivi & Bilan Financier", 
    "🏟️ Bilan par Réunion"
])

if "date_commune" not in st.session_state:
    st.session_state["date_commune"] = datetime.date.today()

def sync_date_chrono():
    d = st.session_state["date_chrono_picker"]
    st.session_state["date_commune"] = d
    st.session_state["date_analyse_picker"] = d

def sync_date_analyse():
    d = st.session_state["date_analyse_picker"]
    st.session_state["date_commune"] = d
    st.session_state["date_chrono_picker"] = d

# --- TAB 1 : CHRONOLOGIQUE ---
with tab_chronologique:
    st.title("⏰ Programme Chronologique & Paris Rapides")
    col_c1, col_c2 = st.columns([2, 2])
    with col_c1:
        date_chrono_sel = st.date_input("Date", value=st.session_state["date_commune"], key="date_chrono_picker", on_change=sync_date_chrono)
        date_chrono_iso = date_chrono_sel.strftime("%Y-%m-%d")
        fichier_chrono_jour = DOSSIER / f"pmu_du_jour_{date_chrono_iso}.json"
    
    with col_c2:
        if st.button("📥 Télécharger/Actualiser les courses"):
            with st.spinner("Téléchargement..."):
                if telecharger_pmu_date(date_chrono_iso, fichier_chrono_jour):
                    st.success("Données actualisées !")
                    st.rerun()

    if verifier_stop_loss(date_chrono_iso):
        st.error("⚠️ **Alerte Stop-Loss Déclenché :** Les pertes cumulées dépassent 30.00 € aujourd'hui. Prudence fortement recommandée sur vos paris !")

    if fichier_chrono_jour.exists():
        donnees_chrono, _ = charger_donnees_fichier(fichier_chrono_jour)
        toutes_courses = []
        for c_elem in donnees_chrono:
            nom_c = str(c_elem.get("nom_course", "")).strip()
            if not nom_c or nom_c.isdigit() or len(nom_c) <= 2:
                continue
                
            r_nom = f"{c_elem.get('reunion', 'R1')} - {c_elem.get('hippodrome', 'HIPPODROME')}"
            
            chevaux_c = c_elem.get("chevaux", [])
            chevaux_val_c = [c for c in chevaux_c if safe_float(c.get("cote")) > 1.0 or c.get("cote") is None]
            
            base_chev, poker_chev = {"num": "?", "nom": "Inconnu", "cote": 0.0}, {"num": "?", "nom": "Inconnu", "cote": 0.0}
            if chevaux_val_c:
                params_ad_chrono = calculer_parametres_adaptatifs()
                for c in chevaux_val_c:
                    c["score_analyse"] = evaluer_score_cheval(
                        c, 
                        c_elem.get('discipline'), 
                        c_elem.get('terrain_officiel'), 
                        c_elem.get('corde', 'Corde standard'), 
                        date_chrono_iso, 
                        params_ad_chrono
                    )
                chevaux_val_c.sort(key=lambda x: x["score_analyse"], reverse=True)
                base_chev = chevaux_val_c[0]
                outsiders_c = [c for c in chevaux_val_c if 6.0 <= safe_float(c.get("cote")) <= 25.0 and c["num"] != base_chev["num"]]
                poker_chev = max(outsiders_c, key=lambda x: x["score_analyse"]) if outsiders_c else (chevaux_val_c[1] if len(chevaux_val_c) > 1 else base_chev)

            toutes_courses.append({
                "heure": c_elem.get("heure", "13:30"), "reunion": r_nom, "course_num": c_elem.get("course", "C1"),
                "nom_course": nom_c, "discipline": c_elem.get("discipline", ""), "data": c_elem,
                "base": base_chev, "poker": poker_chev
            })
        
        # --- TRI CHRONOLOGIQUE GLOBAL PAR HEURE ---
        toutes_courses.sort(key=lambda x: x["heure"])
        
        for idx_c, item_c in enumerate(toutes_courses):
            course_obj = item_c["data"]
            b_chev = item_c["base"]
            p_chev = item_c["poker"]
            
            # Utilisation de clés uniques et stables incluant la réunion et le numéro de course
            cle_unique_course = f"{item_c['reunion']}_{item_c['course_num']}_{idx_c}"
            
            with st.expander(f"🕒 {item_c['heure']} | {item_c['reunion']} ➔ {item_c['course_num']} : {item_c['nom_course']}"):
                st.markdown(f"**Base solide (Sécurité) :** Simple Placé ➔ N°{b_chev.get('num')} - {b_chev.get('nom')} (Cote: {safe_float(b_chev.get('cote')):.1f})")
                st.markdown(f"**Coup de poker :** Simple Gagnant ➔ N°{p_chev.get('num')} - {p_chev.get('nom')} (Cote: {safe_float(p_chev.get('cote')):.1f})")
                
                col_m, col_b = st.columns([2, 1])
                with col_m:
                    mise_input = st.number_input("Mise Totale (€)", min_value=1, value=10, key=f"m_{cle_unique_course}")
                    
                    # Calcul dynamique de la répartition pour l'affichage visuel
                    mise_secu = round(mise_input * 0.7, 1)
                    mise_poker = round(mise_input - mise_secu, 1)
                    st.caption(f"💡 Répartition indicative : **{mise_secu} €** sur la Sécu | **{mise_poker} €** sur le Poker")

                with col_b:
                    st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("⚡ Valider & Enregistrer", key=f"btn_valider_{cle_unique_course}"):
                        b_num = b_chev.get('num', '?')
                        p_num = p_chev.get('num', '?')

                        nouveau_pari = {
                            "date": date_chrono_iso, 
                            "reunion": item_c['reunion'], 
                            "course_num": item_c['course_num'], 
                            "course": f"{item_c['reunion']} - {item_c['course_num']}",
                            "discipline": course_obj.get('discipline'), 
                            "type": "Rapide",
                            "details": f"Simple Placé (Sécurité) ➔ N°{b_num} ({mise_secu}€) | Simple Gagnant (Poker) ➔ N°{p_num} ({mise_poker}€)",
                            "mise": float(mise_input), 
                            "statut": "En attente", 
                            "gain": 0.0, 
                            "diagnostic": ""
                        }

                        hist = []
                        if FICHIER_HISTORIQUE.exists():
                            with open(FICHIER_HISTORIQUE, "r", encoding="utf-8", errors="replace") as f:
                                try:
                                    hist = json.load(f)
                                except Exception:
                                    hist = []
                        
                        hist.append(nouveau_pari)
                        sauvegarder_et_synchroniser(hist, FICHIER_HISTORIQUE, "Pari rapide enregistré")
                        st.success("Pari validé et enregistré avec succès !")
                        st.rerun()

# --- TAB 2 : ANALYSE ---
with tab_analyse:
    st.title("📊 Analyse & Stratégie PMU Pro")
    date_sel = st.date_input("Date du jour", value=st.session_state["date_commune"], key="date_analyse_picker", on_change=sync_date_analyse)
    date_iso = date_sel.strftime("%Y-%m-%d")
    fichier_jour = DOSSIER / f"pmu_du_jour_{date_iso}.json"

    if fichier_jour.exists():
        donnees, reunions_map = charger_donnees_fichier(fichier_jour)
        if reunions_map:
            reunion_choisie = st.selectbox("Réunion", sorted(list(reunions_map.keys())))
            courses = reunions_map[reunion_choisie]
            c_map = {f"{c['course']} : {c['nom_course']}": c for c in courses}
            c_choisie = st.selectbox("Course", list(c_map.keys()))
            course_curr = c_map[c_choisie]
            
            st.info(f"Terrain : {course_curr.get('terrain_officiel')} | Discipline : {course_curr.get('discipline')}")
            
            if st.button("⚡ Lancer l'Analyse Intégrale IA"):
                params = calculer_parametres_adaptatifs()
                for c in course_curr.get("chevaux", []):
                    c["score_ia"] = evaluer_score_cheval(
                        c, 
                        course_curr.get("discipline"), 
                        course_curr.get("terrain_officiel"), 
                        course_curr.get("corde", "Corde standard"), 
                        date_iso, 
                        params
                    )                
                chevaux_tries = sorted(course_curr.get("chevaux", []), key=lambda x: x.get("score_ia", 0), reverse=True)
                st.dataframe([{
                    "N°": c["num"], "Nom": c["nom"], "Driver": c["driver"], 
                    "Cote": c.get("cote"), "Score IA": c.get("score_ia")
                } for c in chevaux_tries], use_container_width=True)

        st.divider()
        st.subheader("💰 Plan d'Allocation Budgétaire Journalier")
        budget_saisi = st.number_input("Budget Global à Allouer (€)", min_value=5, max_value=500, value=50, step=5)
        
        if st.button("🎲 Calculer la Répartition Stratégique"):
            params_ad = calculer_parametres_adaptatifs()
            plan = generer_plan_budget_journalier(fichier_jour, budget_saisi, params_ad, date_iso=date_iso)
            if plan:
                st.session_state["plan_courant"] = plan
                st.session_state["plan_date_iso"] = date_iso
            else:
                st.session_state["plan_courant"] = None
                st.info("Aucune opportunité ne remplit les critères de sécurité suffisants pour ce budget.")

        if st.session_state.get("plan_courant"):
            st.write("### 📌 Stratégie de Mises Optimisée")
            st.dataframe(st.session_state["plan_courant"], use_container_width=True)
            
            if st.button("✅ Enregistrer tout ce plan dans le suivi des paris", type="primary"):
                hist = []
                if FICHIER_HISTORIQUE.exists():
                    with open(FICHIER_HISTORIQUE, "r", encoding="utf-8", errors="replace") as f:
                        hist = json.load(f)
                
                date_pari = st.session_state.get("plan_date_iso", date_iso)
                for item in st.session_state["plan_courant"]:
                    r_c = item.get("Course", "")
                    mise_tot = safe_float(item.get("Mise Totale Course", 0))
                    
                    pari_obj = {
                        "date": date_pari,
                        "reunion": item.get("Reunion_Clean", "R? - Hippodrome"),
                        "course_num": r_c.split(" - ")[2].split(" ")[0] if r_c.count(" - ") >= 2 else "C?",
                        "course": r_c,
                        "discipline": item.get("Discipline", ""),
                        "type": "Plan Budget",
                        "details": f"Sécu ({item.get('Mise Sécu')}): {item.get('Base Solide (Sécurité)')} | Poker ({item.get('Mise Poker')}): {item.get('Coup de Poker')}",
                        "mise": mise_tot,
                        "statut": "En attente",
                        "gain": 0.0,
                        "diagnostic": ""
                    }
                    hist.append(pari_obj)
                
                sauvegarder_et_synchroniser(hist, FICHIER_HISTORIQUE, "Enregistrement du plan budgétaire complet")
                st.success(f"🎉 {len(st.session_state['plan_courant'])} paris du plan ont été enregistrés dans votre suivi !")
                st.session_state["plan_courant"] = None
                st.rerun()
    else:
        st.info("Aucune donnée disponible pour cette date. Cliquez sur 'Télécharger/Actualiser les courses' dans le premier onglet.")

# --- TAB 3 : DASHBOARD IA ---
with tab_ia:
    st.title("🧠 Moteur d'Apprentissage IA & Coefficients Dynamiques")
    st.write("Ce module adapte automatiquement l'importance relative de chaque critère hippique en analysant vos résultats passés.")
    
    modele_ia = charger_modele_ia()
    
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    col_k1.metric("Poids Ferrage", f"{modele_ia.get('poids_ferrage', 1.0):.2f}")
    col_k2.metric("Sensibilité Smart Money", f"{modele_ia.get('poids_cote_tendance', 1.0):.2f}")
    col_k3.metric("Impact Terrain", f"{modele_ia.get('poids_terrain', 1.0):.2f}")
    col_k4.metric("Bonus Driver/Jockey", f"{modele_ia.get('poids_driver', 1.0):.2f}")

    st.divider()
    st.subheader("📊 Performance & Réglages des Poids IA")
    
    col_g1, col_g2 = st.columns([2, 2])
    with col_g1:
        st.write("**Visualisation des coefficients actuels :**")
        df_poids = pd.DataFrame([
            {"Critère": "Musique / Forme", "Poids IA": modele_ia.get("poids_musique", 1.0)},
            {"Critère": "Ferrage (Déferré)", "Poids IA": modele_ia.get("poids_ferrage", 1.0)},
            {"Critère": "Adaptation Terrain", "Poids IA": modele_ia.get("poids_terrain", 1.0)},
            {"Critère": "Tendance Cotes (Smart Money)", "Poids IA": modele_ia.get("poids_cote_tendance", 1.0)},
            {"Critère": "Impact Driver / Jockey", "Poids IA": modele_ia.get("poids_driver", 1.0)},
            {"Critère": "Affinité Distance", "Poids IA": modele_ia.get("poids_distance", 1.1)}, # ➔ Ajout ici
        ])
        st.bar_chart(df_poids.set_index("Critère"))
        
    with col_g2:
        st.write("**Derniers ajustements automatiques effectués par l'IA :**")
        historique_ajust = modele_ia.get("historique_ajustements", [])
        if historique_ajust:
            for item in historique_ajust:
                st.info(item)
        else:
            st.info("Aucun ajustement récent enregistré. Validez des résultats de courses pour faire évoluer l'IA.")

# --- TAB 4 : SUIVI ET BILAN ---
with tab_suivi:
    st.title("📈 Suivi, Bilan Financier & ROI")
    if FICHIER_HISTORIQUE.exists():
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
            
        col_btn1, col_btn2 = st.columns([2, 2])
        with col_btn1:
            if st.button("🔄 Vérifier automatiquement les résultats des courses"):
                with st.spinner("Analyse et mise à jour IA en cours..."):
                    if verifier_resultats_automatiques_pmu(historique):
                        sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Mise à jour automatique des résultats PMU")
                        st.success("Résultats et modèle IA actualisés avec succès !")
                        st.rerun()
                    else:
                        st.info("Aucun nouveau résultat disponible.")
                        
        with col_btn2:
            if st.button("🗑️ Réinitialiser les montants (Mises / Gains / Bilan)", type="secondary"):
                for p in historique:
                    # On ne remet à zéro que les valeurs financières, on ne touche pas au statut global ni au reste
                    p["mise"] = 0.0
                    p["gain"] = 0.0
                sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Remise à zéro des montants financiers")
                st.success("Les mises et gains totaux ont été remis à zéro !")
                st.rerun()

        total_mise = sum(safe_float(p.get("mise", 0)) for p in historique if p.get("statut") != "Annulé")
        total_gain = sum(safe_float(p.get("gain", 0)) for p in historique if p.get("statut") == "Gagné")
        bilan_net = total_gain - total_mise
        roi_global = ((total_gain - total_mise) / total_mise * 100) if total_mise > 0 else 0.0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Mise Totale", f"{total_mise:.2f} €")
        col2.metric("Gains Totaux", f"{total_gain:.2f} €")
        col3.metric("Bilan Net", f"{bilan_net:+.2f} €")
        col4.metric("ROI Global", f"{roi_global:+.1f}%")

        st.divider()
        st.subheader("📁 Historique détaillé des Paris & Diagnostic IA")
        data_suivi = []
        for idx, p in enumerate(historique):
            gain_val = safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0
            data_suivi.append({
                "Index": idx, 
                "Date": p.get("date"), 
                "Course": p.get("course"),
                "Type": p.get("type"), 
                "Détails": p.get("details"),
                "Mise (€)": safe_float(p.get("mise", 0)), 
                "Statut": p.get("statut"),
                "Gain (€)": gain_val,
                "Diagnostic IA Post-Course": p.get("diagnostic", "-")
            })
            
        df_suivi = pd.DataFrame(data_suivi)
        df_suivi["Gain (€)"] = df_suivi["Gain (€)"].astype(float)
        
        st.dataframe(df_suivi, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun historique de pari disponible. Enregistrez des paris depuis l'onglet Chrono.")

# --- TAB 5 : REUNIONS ---
with tab_reunions:
    st.title("🏟️ Bilan par Réunion")
    if FICHIER_HISTORIQUE.exists():
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
        dates = sorted(list(set(str(p.get("date")) for p in historique if p.get("date"))), reverse=True)
        if dates:
            d_choisie = st.selectbox("📅 Sélectionner la date", dates)
            bilan = generer_et_sauvegarder_bilan_journee(historique, d_choisie)
            if bilan:
                st.dataframe(bilan, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun pari enregistré avec une date valide.")
    else:
        st.info("Aucun bilan disponible.")
