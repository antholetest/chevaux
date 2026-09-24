import datetime
import json
from pathlib import Path
import streamlit as st
import requests
import subprocess
import re
import random
import pandas as pd
import threading

# Configuration de la page Streamlit pour mobile et PC
st.set_page_config(
    page_title="Analyse & Stratégie PMU Pro + IA Maximisation des Gains",
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

# --- FONCTIONS UTILITAIRES DE CONVERSION & RÉGULARISATION ---
def safe_float(val, default=0.0):
    if val is None or val == "" or val == "-":
        return default
    try:
        return float(str(val).replace(",", ".").replace("€", "").strip())
    except (ValueError, TypeError):
        return default

def amortir_poids(valeur, cible=1.0, facteur=0.01):
    """Ramène doucement les poids vers la valeur neutre (1.0) pour éviter le blocage aux plafonds."""
    return valeur + (cible - valeur) * facteur

def normaliser_scores_chevaux(chevaux, cle_score="score_analyse"):
    """Ramène les scores calculés d'une course sur une échelle relative de 0 à 100."""
    if not chevaux:
        return chevaux
    score_max = max((safe_float(c.get(cle_score, 0)) for c in chevaux), default=0.0)
    if score_max > 0:
        for c in chevaux:
            c[cle_score] = round((safe_float(c.get(cle_score, 0)) / score_max) * 100, 1)
    return chevaux

# --- SYNCHRONISATION GITHUB (ASYNCHRONE) ---
def tache_git_background(filename_path_str, message):
    try:
        if "GITHUB_TOKEN" in st.secrets:
            token = st.secrets["GITHUB_TOKEN"]
            subprocess.run(["git", "config", "--global", "user.email", "bot@streamlit.app"], capture_output=True)
            subprocess.run(["git", "config", "--global", "user.name", "Streamlit Bot"], capture_output=True)
            subprocess.run(["git", "add", filename_path_str], check=True, capture_output=True)
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if filename_path_str in status.stdout:
                subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
                repo_url = f"https://{token}@github.com/antholetest/chevaux.git"
                res_push = subprocess.run(["git", "push", repo_url], capture_output=True, text=True)
                if res_push.returncode != 0:
                    subprocess.run(["git", "push", repo_url, "HEAD"], capture_output=True)
    except Exception:
        pass

def sauvegarder_et_synchroniser(data, filename, message="Mise à jour automatique PMU"):
    filename_path = Path(filename)
    with open(filename_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    threading.Thread(target=tache_git_background, args=(str(filename_path.name), message)).start()
    st.toast("Données enregistrées !", icon="💾")

# --- MODULE IA : GESTION DU MODÈLE ET DES POIDS DYNAMIQUES ---
MODELE_IA_DEFAUT = {
    "poids_musique": 1.05,
    "poids_ferrage": 1.25,
    "poids_terrain": 1.15,
    "poids_poids": 1.0,
    "poids_cote_tendance": 1.35,
    "poids_driver": 1.15,
    "poids_corde": 1.0,
    "poids_hippodrome_acteur": 1.25,
    "poids_distance": 1.1,
    "poids_outsider_cache": 1.30,
    "seuil_value_bet": 1.05,      # Seuil minimal d'espérance de gain
    "frequence_kelly": 0.25,      # Fraction du critère de Kelly pour le staking
    "stats_impact": {
        "victoires_par_ferrage": 0,
        "victoires_par_smart_money": 0,
        "victoires_par_terrain": 0,
        "victoires_par_hippodrome": 0,
        "victoires_par_distance": 0,
        "total_analyses": 0,
        "gain_cumule_ia": 0.0
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
    cles_poids = [
        "poids_musique", "poids_ferrage", "poids_terrain", "poids_poids", 
        "poids_cote_tendance", "poids_driver", "poids_corde", 
        "poids_hippodrome_acteur", "poids_distance", "poids_outsider_cache"
    ]
    for cle in cles_poids:
        if cle in modele:
            modele[cle] = max(0.7, min(1.5, float(modele[cle])))

    sauvegarder_et_synchroniser(modele, FICHIER_MODELE_IA, "Mise à jour automatique du modèle IA (Optimisation Gain)")

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
                        
                        rapport_ref = p.get("rapportReference")
                        cote_ouv = rapport_ref.get("rapport") if isinstance(rapport_ref, dict) else cote_val
                        
                        tendance = "stable"
                        if cote_val and cote_ouv:
                            if cote_val < cote_ouv * 0.85:
                                tendance = "baisse_forte"
                            elif cote_val > cote_ouv * 1.15:
                                tendance = "hausse"
                                
                        chevaux.append({
                            "num": p.get("numPmu"),
                            "nom": p.get("nom"),
                            "driver": p.get("driver", p.get("jockey", "")),
                            "musique": p.get("musique", ""),
                            "deferre": p.get("deferre", ""),
                            "poids": safe_float(p.get("poids", 0.0)),
                            "cote": cote_val,
                            "tendance_cote": tendance
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
    if not distance_course:
        return 1.0
    return 1.1

@st.cache_data(ttl=3600)
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
            
    bonus_hippodrome = min(apparitions_hippodrome * 1.0, 6.0)
    bonus_global = min(apparitions_globales * 0.2, 3.0)
    
    multiplicateur = 1.0 + ((bonus_hippodrome + bonus_global) / 10.0)
    return multiplicateur

# --- DÉTECTION DU STOP-LOSS ---
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

        return perte >= 35.0

    except Exception as e:
        print(f"Erreur lecture stop-loss : {e}")
        return False

@st.cache_data(ttl=60)
def calculer_parametres_adaptatifs():
    params = {
        "bonus_place": 0, 
        "malus_discipline": {}, 
        "types_privilegies": ["Simple", "Couplé"],
        "message_auto": "Algorithme de maximisation des gains actif."
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
                params["bonus_place"] = int(round(taux * 12))
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
            if vals["nb"] >= 8 and vals["mises"] >= 50.0:
                mises_val = vals["mises"]
                if mises_val > 0:
                    roi = ((vals["gains"] - mises_val) / mises_val) * 100
                    if roi < -20.0:
                        params["malus_discipline"][disc] = -3
                        messages.append(f"⚠️ Discipline '{disc}' en déficit ({roi:.1f}% ROI) -> Malus -3 pts")
                    elif roi > 10.0:
                        messages.append(f"🔥 Discipline '{disc}' à haut ROI (+{roi:.1f}%) -> Priorisée")

        params["message_auto"] = " | ".join(messages) if messages else "🤖 Modèle Value-Bet & Maximisation des Gains actif."
    except Exception:
        pass
    return params

# --- ÉVALUATION DES CHEVAUX ET CALCUL DE LA VALEUR ESPÉRÉE (EXPECTED VALUE) ---
def evaluer_score_cheval(cheval, discipline, terrain, corde, date_jour, params_adaptatifs, hippodrome="", distance_course=""):
    modele_ia = charger_modele_ia()
    
    score = 0.0
    musique = str(cheval.get("musique") or "").upper()
    deferre = str(cheval.get("deferre") or "").upper()
    driver = str(cheval.get("driver") or "").upper()
    cote = safe_float(cheval.get("cote"), 0.0)
    poids = safe_float(cheval.get("poids", 0.0))
    tendance = cheval.get("tendance_cote", "stable")
    bonus_place = params_adaptatifs.get("bonus_place", 0)

    # 1. Performance Récente & Musique
    score_musique = 0
    for idx, char in enumerate(musique[:8]):
        if char == "1":
            score_musique += 12 if idx >= 3 else 14
        elif char == "2":
            score_musique += 8 + bonus_place
        elif char == "3":
            score_musique += 6 + bonus_place
        elif char in ["4", "5"]:
            score_musique += 2
        elif char in ["0", "D", "T", "A"]:
            score_musique -= (7 if (char in ["D", "T", "A"] and idx < 3) else 4)
    score += score_musique * modele_ia.get("poids_musique", 1.05)

    # 2. Configuration Physico-Technique (Ferrage / Poids / Terrain)
    if "Trot" in str(discipline):
        if "QUATRE" in deferre:
            score += 10.0 * modele_ia.get("poids_ferrage", 1.25)
        elif "ANTERIEURS" in deferre or "POSTERIEURS" in deferre:
            score += 5.5 * modele_ia.get("poids_ferrage", 1.25)
    else:
        if poids > 0:
            if poids < 55.0:
                score += 4.5 * modele_ia.get("poids_poids", 1.0)
            elif poids > 62.0:
                score -= 3.5 * modele_ia.get("poids_poids", 1.0)
        if terrain in ["Collant", "Lourd"] and ("LOURD" in musique or "SOUPLE" in musique):
            score += 7.0 * modele_ia.get("poids_terrain", 1.15)

    # 3. Corde
    poids_corde = modele_ia.get("poids_corde", 1.0)
    corde_str = str(corde).upper()
    if "GAUCHE" in corde_str and ("G" in musique or "GAUCHE" in musique):
        score += 4.5 * poids_corde
    elif "DROITE" in corde_str and ("D" in musique or "DROITE" in musique):
        score += 4.5 * poids_corde
    else:
        score += 1.0 * poids_corde

    # 4. Smart Money & Mouvement des Cotes
    if tendance == "baisse_forte":
        score += 6.5 * modele_ia.get("poids_cote_tendance", 1.35)
    elif tendance == "hausse":
        score -= 3.0 * modele_ia.get("poids_cote_tendance", 1.35)

    # 5. Synergie Acteur / Hippodrome
    mult_acteur = analyser_performances_acteur_par_hippodrome(driver, hippodrome)
    bonus_acteur = (mult_acteur - 1.0) * 10.0
    score += (bonus_acteur * modele_ia.get("poids_driver", 1.15) * modele_ia.get("poids_hippodrome_acteur", 1.25))

    # 6. Affinité de distance
    poids_dist_ia = modele_ia.get("poids_distance", 1.1)
    mult_distance = analyser_affinite_distance(cheval, distance_course)
    bonus_distance = (mult_distance - 1.0) * 5.0
    score += (bonus_distance * poids_dist_ia)

    # 7. Attraction des Cotes & Détection d'Outsider Rentable
    if cote > 1.0:
        if cote < 2.5:
            score += 6
        elif 2.5 <= cote <= 6.0:
            score += 8
        elif 6.0 < cote <= 18.0:
            score += 10
        elif cote > 35.0:
            score -= 2

    # 8. DÉTECTION DU VALUE OUTSIDER (HAUT RENDEMENT)
    poids_outsider = modele_ia.get("poids_outsider_cache", 1.30)
    if 6.0 <= cote <= 30.0:
        bonus_joker = 0.0
        if tendance == "baisse_forte":
            bonus_joker += 9.0
        if "Trot" in str(discipline) and "QUATRE" in deferre:
            bonus_joker += 7.0
        if mult_acteur > 1.2:
            bonus_joker += 6.0
            
        impact_joker = min(15.0, bonus_joker * poids_outsider)
        score += impact_joker

    score += params_adaptatifs.get("malus_discipline", {}).get(discipline, 0)
    return max(0.0, round(score, 1))

# --- CALCUL DU VALEUR ESPÉRÉE (VALUE BET INDEX) ET PROBABILITÉ ESTIMATIVE ---
def calculer_valeur_esperee(chevaux_valides):
    """Calcule l'Espérance de Gain (EV = Proba_Estimee * Cote_Reelle) pour chaque cheval."""
    score_total = sum(safe_float(c.get("score_analyse", 0)) for c in chevaux_valides)
    if score_total <= 0:
        for c in chevaux_valides:
            c["proba_estimee"] = 0.0
            c["ev_index"] = 0.0
        return chevaux_valides

    for c in chevaux_valides:
        score = safe_float(c.get("score_analyse", 0))
        cote = safe_float(c.get("cote"), 0.0)
        proba_estimee = score / score_total
        c["proba_estimee"] = round(proba_estimee, 4)
        
        if cote > 1.0:
            ev = proba_estimee * cote
        else:
            ev = 0.0
        c["ev_index"] = round(ev, 2)
        
    return chevaux_valides

# --- MOTEUR APPRENTISSAGE POST-MORTEM AXÉ SUR LE ROI ET LA RENTABILITÉ ---
def retroaction_apprentissage_ia(pari_item, arrivee_officielle, cotes_reelles, partants_details):
    modele_ia = charger_modele_ia()
    statut = pari_item.get("statut")
    details_pari = str(pari_item.get("details", ""))
    discipline = pari_item.get("discipline", "Galop Plat")
    
    mise_totale = safe_float(pari_item.get("mise", 0))
    gain_total = safe_float(pari_item.get("gain", 0))
    profit_net = gain_total - mise_totale
    
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
        modele_ia["stats_impact"]["total_analyses"] += 1
        modele_ia["stats_impact"]["gain_cumule_ia"] = round(modele_ia["stats_impact"].get("gain_cumule_ia", 0.0) + profit_net, 2)
        
        roi_pari = (profit_net / mise_totale * 100) if mise_totale > 0 else 0.0
        
        if profit_net < 0:
            diagnostic_lignes.append(f"⚠️ **Victoire déficitaire :** Gain ({gain_total:.2f}€) < Mise ({mise_totale:.2f}€).")
            modele_ia["poids_musique"] = max(0.8, modele_ia.get("poids_musique", 1.05) - 0.003)
            modele_ia["poids_outsider_cache"] = min(1.5, modele_ia.get("poids_outsider_cache", 1.3) + 0.008)
            ajustements.append("Ajustement Value : Recherche Outsider ⬆️ (+0.008)")
        else:
            diagnostic_lignes.append(f"🎯 **Victoire rentable (+{profit_net:.2f}€ | ROI: +{roi_pari:.1f}%) !**")
            
            facteur_amplification = min(0.015, 0.003 + (roi_pari / 10000.0))
            
            if cheval_gagnant_obj and safe_float(cheval_gagnant_obj.get("cote")) >= 6.0:
                modele_ia["poids_outsider_cache"] = min(1.5, modele_ia.get("poids_outsider_cache", 1.3) + facteur_amplification)
                modele_ia["poids_cote_tendance"] = min(1.5, modele_ia.get("poids_cote_tendance", 1.35) + facteur_amplification)
                ajustements.append(f"Validation High Value ⬆️ (+{facteur_amplification:.3f})")
        
        if cheval_gagnant_obj:
            def_gagnant = str(cheval_gagnant_obj.get("deferre", "")).upper()
            if "QUATRE" in def_gagnant and "Trot" in str(discipline):
                modele_ia["poids_ferrage"] = min(1.5, modele_ia.get("poids_ferrage", 1.25) + 0.004)
                modele_ia["stats_impact"]["victoires_par_ferrage"] += 1
                ajustements.append("Poids Ferrage Trot ⬆️ (+0.004)")

    elif statut == "Perdu":
        modele_ia["stats_impact"]["gain_cumule_ia"] = round(modele_ia["stats_impact"].get("gain_cumule_ia", 0.0) - mise_totale, 2)
        diagnostic_lignes.append("⚠️ **Analyse de l'échec :**")
        top_4_5 = arrivee_officielle[3:5] if len(arrivee_officielle) >= 5 else []
        presence_proche = any(n in nums_paries for n in top_4_5)
        
        if presence_proche:
            diagnostic_lignes.append("• *Quasi-podium (4e/5e) :* Très proche du gain.")
            modele_ia["poids_musique"] = min(1.5, modele_ia.get("poids_musique", 1.05) + 0.003)
            ajustements.append("Poids Musique ⬆️ (+0.003)")
        else:
            cote_gagnant = cotes_reelles.get(gagnant_reel_num, 0.0)
            if cote_gagnant > 12.0:
                diagnostic_lignes.append(f"• *Outsider rentable manqué :* N°{gagnant_reel_num} à {cote_gagnant:.1f}.")
                modele_ia["poids_cote_tendance"] = min(1.5, modele_ia.get("poids_cote_tendance", 1.35) + 0.004)
                modele_ia["poids_outsider_cache"] = min(1.5, modele_ia.get("poids_outsider_cache", 1.3) + 0.006)
                ajustements.append("Augmentation Sensibilité Smart Money & Outsider ⬆️")
            else:
                diagnostic_lignes.append("• *Élimination de valeur.*")
                if "Trot" in str(discipline) and cheval_gagnant_obj:
                    def_gagnant = str(cheval_gagnant_obj.get("deferre", "")).upper()
                    if "QUATRE" in def_gagnant:
                        modele_ia["poids_ferrage"] = min(1.5, modele_ia.get("poids_ferrage", 1.25) + 0.003)
                        ajustements.append("Renforcement Ferrage ⬆️ (+0.003)")
                    else:
                        modele_ia["poids_ferrage"] = max(0.7, modele_ia.get("poids_ferrage", 1.25) - 0.002)
                        ajustements.append("Ajustement Ferrage ⬇️ (-0.002)")

    cles_poids = [
        "poids_musique", "poids_ferrage", "poids_terrain", "poids_poids", 
        "poids_cote_tendance", "poids_driver", "poids_corde", 
        "poids_hippodrome_acteur", "poids_distance", "poids_outsider_cache"
    ]
    for cle in cles_poids:
        if cle in modele_ia:
            modele_ia[cle] = max(0.7, min(1.5, amortir_poids(float(modele_ia[cle]))))

    if ajustements:
        horodatage = datetime.datetime.now().strftime("%d/%m %H:%M")
        modele_ia["historique_ajustements"].insert(0, f"[{horodatage}] Course {pari_item.get('course')} -> {', '.join(ajustements)}")
        modele_ia["historique_ajustements"] = modele_ia["historique_ajustements"][:20]
        sauvegarder_modele_ia(modele_ia)

    return "\n".join(diagnostic_lignes)

# --- GÉNÉRATEUR DE PLAN DE BUDGET ET D'ALLOCATION KELLY SUR LES VALUE BETS ---
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
        if malus_disc.get(discipline, 0) <= -3:
            continue
            
        terrain = course.get("terrain_officiel", "Bon (Standard)")
        corde = course.get("corde", "Corde standard")
        chevaux_valides = [c for c in chevaux if safe_float(c.get("cote")) > 1.0 or c.get("cote") is None]
        nb_partants_total = len(chevaux)
        
        if len(chevaux_valides) < 3:
            continue
            
        for c in chevaux_valides:
            c["score_analyse"] = evaluer_score_cheval(c, discipline, terrain, corde, date_iso, params_adaptatifs)
            
        normaliser_scores_chevaux(chevaux_valides, "score_analyse")
        calculer_valeur_esperee(chevaux_valides)
            
        chevaux_tries_score = sorted(chevaux_valides, key=lambda x: x["score_analyse"], reverse=True)
        chevaux_tries_ev = sorted(chevaux_valides, key=lambda x: x["ev_index"], reverse=True)
        
        meilleur_score = chevaux_tries_score[0]
        meilleur_ev = chevaux_tries_ev[0]
        
        if meilleur_ev["ev_index"] <= 1.15:
            continue
            
        ecart_score = meilleur_score["score_analyse"] - chevaux_tries_score[1]["score_analyse"] if len(chevaux_tries_score) > 1 else 10.0
        indice_confiance = ecart_score + (meilleur_ev["ev_index"] * 10)
        
        outsiders = [c for c in chevaux_valides if 5.5 <= safe_float(c.get("cote")) <= 25.0 and c["num"] != meilleur_score["num"]]
        poker = max(outsiders, key=lambda x: x["ev_index"]) if outsiders else (chevaux_tries_score[1] if len(chevaux_tries_score) > 1 else meilleur_score)

        r_nom_complet = f"{course.get('reunion', 'R1')} - {course.get('hippodrome', 'HIPPODROME')}"
        opportunites.append({
            "score_confiance": max(1.0, indice_confiance),
            "ev_max": meilleur_ev["ev_index"],
            "reunion_course": f"{r_nom_complet} - {course.get('course')}",
            "reunion_clean": r_nom_complet,
            "nom_course": course.get('nom_course'),
            "discipline": discipline,
            "meilleur_cheval": meilleur_score,
            "poker": poker,
            "nb_partants": nb_partants_total
        })
        
    opportunites.sort(key=lambda x: (x["ev_max"], x["score_confiance"]), reverse=True)
    if not opportunites:
        return []

    max_courses = 1 if budget_total_effectif < 25.0 else (2 if budget_total_effectif < 60.0 else 3)
    top_courses = opportunites[:max_courses]

    somme_ev = sum(c["ev_max"] for c in top_courses)
    brutes_mises = [(budget_total_effectif * (c["ev_max"] / somme_ev)) for c in top_courses] if somme_ev > 0 else [budget_total_effectif / len(top_courses)] * len(top_courses)
    mises_allouees = [max(1, int(round(m))) for m in brutes_mises]
    
    diff = int(budget_total_effectif) - sum(mises_allouees)
    if diff != 0 and mises_allouees:
        mises_allouees[0] = max(1, mises_allouees[0] + diff)

    plan_paris = []
    for idx, course_opt in enumerate(top_courses):
        mise_course = mises_allouees[idx]
        chev_base, chev_poker = course_opt["meilleur_cheval"], course_opt["poker"]
        cote_secu = safe_float(chev_base.get("cote"), 3.0)
        ev_base = chev_base.get("ev_index", 1.0)
        
        ratio_secu = 0.65 if ev_base > 1.2 else 0.75
        mise_secu = max(1, int(round(mise_course * ratio_secu)))
        mise_poker = max(0, mise_course - mise_secu)
        cote_poker = safe_float(chev_poker.get("cote"), 5.0)
        
        plan_paris.append({
            "Reunion_Clean": course_opt["reunion_clean"],
            "Course": course_opt["reunion_course"],
            "Discipline": course_opt["discipline"],
            "Base Value Bet (Sécurité)": f"Simple Placé ➔ N°{chev_base['num']} - {chev_base['nom']} (Cote: {cote_secu:.1f} | EV: {ev_base:.2f})",
            "Mise Sécu": f"{mise_secu} €",
            "Coup de Poker Value": f"Simple Gagnant ➔ N°{chev_poker['num']} - {chev_poker['nom']} (Cote: {cote_poker:.1f} | EV: {chev_poker.get('ev_index', 0):.2f})" if mise_poker > 0 else "Aucun",
            "Mise Poker": f"{mise_poker} €",
            "Mise Totale Course": f"{mise_course} €"
        })
        
    return plan_paris

# --- BILAN AUTOMATISÉ PAR RÉUNION ---
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

    tot_paris = sum(v["paris_total"] for v in reunions_bilan.values())
    tot_gagnes = sum(v["gagnes"] for v in reunions_bilan.values())
    tot_perdus = sum(v["perdus"] for v in reunions_bilan.values())
    tot_attente = sum(v["en_attente"] for v in reunions_bilan.values())
    tot_mises = sum(v["mises"] for v in reunions_bilan.values())
    tot_gains = sum(v["gains"] for v in reunions_bilan.values())
    tot_net = tot_gains - tot_mises
    tot_roi = (tot_net / tot_mises * 100) if tot_mises > 0 else 0.0

    bilan_data.append({
        "Réunion / Hippodrome": "TOTAL",
        "Total Paris": tot_paris,
        "Gagnés": tot_gagnes,
        "Perdus": tot_perdus,
        "En attente": tot_attente,
        "Mises (€)": round(tot_mises, 2),
        "Gains (€)": round(tot_gains, 2),
        "Bilan Net (€)": round(tot_net, 2),
        "ROI (%)": round(tot_roi, 1)
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
                    mise_part_m = re.search(r'\((\d+(?:[\.,]\d+)?)\s*€\)', part)
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
                            gain_total += mise_part * div_ref
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

# --- MODULE ADMINISTRATION ET APPRENTISSAGE IA ---
st.sidebar.divider()
with st.sidebar.expander("🛠️ Administration et réinitialisation"):
    st.write("Gestion des historiques et apprentissage accéléré sur Value Bets.")
    mdp_admin = st.text_input("Code Admin", type="password", key="input_mdp_admin")
    
    if st.button("🔥 Remise à zéro totale", type="primary"):
        if mdp_admin.strip() == st.secrets.get("PASSWORD", "301180"):
            nb = reinitialiser_application_complete()
            st.success(f"Application et IA réinitialisées ({nb} fichiers purgés).")
            st.rerun()
        else:
            st.error("Mot de passe admin incorrect.")
            
    st.divider()
    
    st.write("🤖 **Nourrir l'IA :** Parier sur toutes les courses")
    if st.button("🚀 Simuler le Chrono (10€/course)"):
        if mdp_admin.strip() == st.secrets.get("PASSWORD", "301180"):
            date_iso = st.session_state.get("date_commune", datetime.date.today()).strftime("%Y-%m-%d")
            fichier_jour = DOSSIER / f"pmu_du_jour_{date_iso}.json"
            
            if fichier_jour.exists():
                donnees_chrono, _ = charger_donnees_fichier(fichier_jour)
                hist = []
                if FICHIER_HISTORIQUE.exists():
                    with open(FICHIER_HISTORIQUE, "r", encoding="utf-8", errors="replace") as f:
                        try:
                            hist = json.load(f)
                        except Exception:
                            hist = []
                            
                paris_ajoutes = 0
                params_ad_chrono = calculer_parametres_adaptatifs()
                
                for c_elem in donnees_chrono:
                    if not c_elem.get("nom_course") or len(str(c_elem.get("nom_course"))) <= 2:
                        continue
                        
                    r_nom = f"{c_elem.get('reunion', 'R1')} - {c_elem.get('hippodrome', 'HIPPODROME')}"
                    chevaux_val_c = [c for c in c_elem.get("chevaux", []) if safe_float(c.get("cote")) > 1.0 or c.get("cote") is None]
                    
                    if chevaux_val_c:
                        for c in chevaux_val_c:
                            c["score_analyse"] = evaluer_score_cheval(
                                c, c_elem.get('discipline'), c_elem.get('terrain_officiel'), 
                                c_elem.get('corde', 'Corde standard'), date_iso, params_ad_chrono
                            )
                        normaliser_scores_chevaux(chevaux_val_c, "score_analyse")
                        calculer_valeur_esperee(chevaux_val_c)
                        
                        chevaux_val_c.sort(key=lambda x: (x.get("ev_index", 0), x["score_analyse"]), reverse=True)
                        base_chev = chevaux_val_c[0]
                        
                        if base_chev.get("ev_index", 0) > 1.15:
                            outsiders_c = [c for c in chevaux_val_c if 5.5 <= safe_float(c.get("cote")) <= 25.0 and c["num"] != base_chev["num"]]
                            poker_chev = max(outsiders_c, key=lambda x: x.get("ev_index", 0)) if outsiders_c else (chevaux_val_c[1] if len(chevaux_val_c) > 1 else base_chev)
                            
                            hist.append({
                                "date": date_iso, 
                                "reunion": r_nom, 
                                "course_num": c_elem.get('course', 'C?'), 
                                "course": f"{r_nom} - {c_elem.get('course', 'C?')}",
                                "discipline": c_elem.get('discipline'), 
                                "type": "Rapide (Massif Value)",
                                "details": f"Simple Placé (Sécurité Value) ➔ N°{base_chev.get('num', '?')} (7.0€) | Simple Gagnant (Poker Value) ➔ N°{poker_chev.get('num', '?')} (3.0€)",
                                "mise": 10.0, 
                                "statut": "En attente", 
                                "gain": 0.0, 
                                "diagnostic": ""
                            })
                            paris_ajoutes += 1
                        
                if paris_ajoutes > 0:
                    sauvegarder_et_synchroniser(hist, FICHIER_HISTORIQUE, f"Ajout de {paris_ajoutes} paris apprentissage IA")
                    st.success(f"✅ {paris_ajoutes} paris ajoutés avec succès !")
                    import time
                    time.sleep(2)
                    st.rerun()
                else:
                    st.warning("Aucune course valide à parier aujourd'hui (aucun Value Bet).")
            else:
                st.error("Aucune donnée trouvée. Veuillez télécharger les courses du jour.")
        else:
            st.error("Mot de passe admin incorrect.")

# --- INTERFACE UTILISATEUR STREAMLIT ---
tab_chronologique, tab_analyse, tab_ia, tab_suivi, tab_reunions = st.tabs([
    "⏰ Chrono des Courses", 
    "📊 Analyse & Value Bets", 
    "🧠 Moteur IA & Maximisation Gains",
    "📈 Suivi & ROI Financier", 
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
    st.title("⏰ Programme Chronologique & Sélection Value Bets")
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
        st.error("⚠️ **Alerte Stop-Loss Déclenché :** Les pertes cumulées dépassent 35.00 € aujourd'hui.")

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
            
            base_chev, poker_chev = {"num": "?", "nom": "Inconnu", "cote": 0.0, "ev_index": 0.0}, {"num": "?", "nom": "Inconnu", "cote": 0.0, "ev_index": 0.0}
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
                normaliser_scores_chevaux(chevaux_val_c, "score_analyse")
                calculer_valeur_esperee(chevaux_val_c)
                
                chevaux_val_c.sort(key=lambda x: (x.get("ev_index", 0), x["score_analyse"]), reverse=True)
                base_chev = chevaux_val_c[0]
                outsiders_c = [c for c in chevaux_val_c if 5.5 <= safe_float(c.get("cote")) <= 25.0 and c["num"] != base_chev["num"]]
                poker_chev = max(outsiders_c, key=lambda x: x.get("ev_index", 0)) if outsiders_c else (chevaux_val_c[1] if len(chevaux_val_c) > 1 else base_chev)

            toutes_courses.append({
                "heure": c_elem.get("heure", "13:30"), "reunion": r_nom, "course_num": c_elem.get("course", "C1"),
                "nom_course": nom_c, "discipline": c_elem.get("discipline", ""), "data": c_elem,
                "base": base_chev, "poker": poker_chev
            })
        
        toutes_courses.sort(key=lambda x: x["heure"])
        
        for idx_c, item_c in enumerate(toutes_courses):
            course_obj = item_c["data"]
            b_chev = item_c["base"]
            p_chev = item_c["poker"]
            
            cle_unique_course = f"{item_c['reunion']}_{item_c['course_num']}_{idx_c}"
            
            with st.expander(f"🕒 {item_c['heure']} | {item_c['reunion']} ➔ {item_c['course_num']} : {item_c['nom_course']}"):
                st.markdown(f"**Base Value Bet (Sécurité) :** Simple Placé ➔ N°{b_chev.get('num')} - {b_chev.get('nom')} (Cote: {safe_float(b_chev.get('cote')):.1f} | **EV: {b_chev.get('ev_index', 0):.2f}**) ")
                st.markdown(f"**Coup de Poker Value :** Simple Gagnant ➔ N°{p_chev.get('num')} - {p_chev.get('nom')} (Cote: {safe_float(p_chev.get('cote')):.1f} | **EV: {p_chev.get('ev_index', 0):.2f}**) ")
                
                col_m, col_b = st.columns([2, 1])
                with col_m:
                    mise_input = st.number_input("Mise Totale (€)", min_value=1, value=10, key=f"m_{cle_unique_course}")
                    mise_secu = round(mise_input * 0.7, 1)
                    mise_poker = round(mise_input - mise_secu, 1)
                    st.caption(f"💡 Répartition Optimisée : **{mise_secu} €** Sécu | **{mise_poker} €** Poker")

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
                            "type": "Rapide Value",
                            "details": f"Simple Placé (Sécurité Value) ➔ N°{b_num} ({mise_secu}€) | Simple Gagnant (Poker Value) ➔ N°{p_num} ({mise_poker}€)",
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
                        st.success("Pari validé et enregistré !")
                        st.rerun()

# --- TAB 2 : ANALYSE & VALUE BETS ---
with tab_analyse:
    st.title("📊 Analyse Intégrale & Détection de Value Bets")
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
            
            if st.button("⚡ Lancer l'Analyse Maximisation Gains IA"):
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
                normaliser_scores_chevaux(course_curr.get("chevaux", []), "score_ia")
                calculer_valeur_esperee(course_curr.get("chevaux", []))
                
                chevaux_tries = sorted(course_curr.get("chevaux", []), key=lambda x: x.get("ev_index", 0), reverse=True)
                st.dataframe([{
                    "N°": c["num"], "Nom": c["nom"], "Driver": c["driver"], 
                    "Cote": c.get("cote"), "Score IA (0-100)": c.get("score_ia"),
                    "Proba Estimée (%)": f"{safe_float(c.get('proba_estimee',0))*100:.1f}%",
                    "Value Index (EV)": c.get("ev_index")
                } for c in chevaux_tries], use_container_width=True)

        st.divider()
        st.subheader("💰 Allocation Stratégique de Bankroll (Critère de Kelly)")
        budget_saisi = st.number_input("Budget Global à Allouer (€)", min_value=5, max_value=500, value=50, step=5)
        
        if st.button("🎲 Calculer le Plan d'Allocation Optimal"):
            params_ad = calculer_parametres_adaptatifs()
            plan = generer_plan_budget_journalier(fichier_jour, budget_saisi, params_ad, date_iso=date_iso)
            if plan:
                st.session_state["plan_courant"] = plan
                st.session_state["plan_date_iso"] = date_iso
            else:
                st.session_state["plan_courant"] = None
                st.info("Aucune opportunité ne présente un avantage mathématique (EV > 1.15) suffisant aujourd'hui.")

        if st.session_state.get("plan_courant"):
            st.write("### 📌 Stratégie de Mises Maximisant le Rendement")
            st.dataframe(st.session_state["plan_courant"], use_container_width=True)
            
            if st.button("✅ Enregistrer tout ce plan de mise", type="primary"):
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
                        "type": "Plan Value Kelly",
                        "details": f"Sécu ({item.get('Mise Sécu')}): {item.get('Base Value Bet (Sécurité)')} | Poker ({item.get('Mise Poker')}): {item.get('Coup de Poker Value')}",
                        "mise": mise_tot,
                        "statut": "En attente",
                        "gain": 0.0,
                        "diagnostic": ""
                    }
                    hist.append(pari_obj)
                
                sauvegarder_et_synchroniser(hist, FICHIER_HISTORIQUE, "Enregistrement plan budgétaire Value")
                st.success("Plan Value enregistré dans le suivi !")
                st.session_state["plan_courant"] = None
                st.rerun()
    else:
        st.info("Aucune donnée disponible pour cette date.")

# --- TAB 3 : DASHBOARD IA MAXIMISATION GAINS ---
with tab_ia:
    st.title("🧠 Moteur d'Apprentissage IA & Paramètres ROI")
    modele_ia = charger_modele_ia()
    
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    col_k1.metric("Poids Ferrage", f"{modele_ia.get('poids_ferrage', 1.25):.2f}")
    col_k2.metric("Sensibilité Smart Money", f"{modele_ia.get('poids_cote_tendance', 1.35):.2f}")
    col_k3.metric("Sensibilité Value Bet", f"{modele_ia.get('poids_outsider_cache', 1.30):.2f}")
    col_k4.metric("Gain Cumulé IA", f"{modele_ia.get('stats_impact', {}).get('gain_cumule_ia', 0.0):+.2f} €")

    st.divider()
    st.subheader("📊 Pondérations Actuelles orientées Rendement")
    
    col_g1, col_g2 = st.columns([2, 2])
    with col_g1:
        df_poids = pd.DataFrame([
            {"Critère": "Musique / Forme", "Poids IA": modele_ia.get("poids_musique", 1.05)},
            {"Critère": "Ferrage (Déferré)", "Poids IA": modele_ia.get("poids_ferrage", 1.25)},
            {"Critère": "Adaptation Terrain", "Poids IA": modele_ia.get("poids_terrain", 1.15)},
            {"Critère": "Tendance Cotes (Smart Money)", "Poids IA": modele_ia.get("poids_cote_tendance", 1.35)},
            {"Critère": "Impact Driver / Jockey", "Poids IA": modele_ia.get("poids_driver", 1.15)},
            {"Critère": "Détection Value Outsider", "Poids IA": modele_ia.get("poids_outsider_cache", 1.30)},
        ])
        st.bar_chart(df_poids.set_index("Critère"))
        
    with col_g2:
        st.write("**Derniers ajustements dynamiques :**")
        historique_ajust = modele_ia.get("historique_ajustements", [])
        if historique_ajust:
            for item in historique_ajust:
                st.info(item)
        else:
            st.info("Aucun ajustement récent.")

# --- TAB 4 : SUIVI ET BILAN FINANCIER ---
with tab_suivi:
    st.title("📈 Suivi Financier & Performance ROI")
    if FICHIER_HISTORIQUE.exists():
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
            
        col_btn1, col_btn2 = st.columns([2, 2])
        with col_btn1:
            if st.button("🔄 Vérifier les résultats et entrainer l'IA"):
                with st.spinner("Analyse du rendement et rétroaction IA..."):
                    if verifier_resultats_automatiques_pmu(historique):
                        sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Mise à jour résultats")
                        st.success("Résultats et modèle IA actualisés !")
                        st.rerun()
                    else:
                        st.info("Aucun nouveau résultat à traiter.")
                        
        with col_btn2:
            with st.popover("🗑️ Réinitialiser les montants"):
                st.warning("⚠️ **Confirmation requise**\n\nCette action va remettre à zéro toutes les mises et tous les gains enregistrés dans l'historique.")
                if st.button("🔥 Confirmer la remise à zéro", type="primary"):
                    for p in historique:
                        p["mise"] = 0.0
                        p["gain"] = 0.0
                    sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Remise à zéro montants")
                    st.success("Montants remis à zéro !")
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
        st.subheader("📁 Historique détaillé des engagements")
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
                "Diagnostic IA": p.get("diagnostic", "-")
            })
            
        df_suivi = pd.DataFrame(data_suivi)
        df_suivi["Gain (€)"] = df_suivi["Gain (€)"].astype(float)
        st.dataframe(df_suivi, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun historique disponible.")

# --- TAB 5 : REUNIONS ---
with tab_reunions:
    st.title("🏟️ Bilan Financier par Réunion")
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
            st.info("Aucune date valide.")
    else:
        st.info("Aucun bilan disponible.")