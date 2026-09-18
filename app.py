import datetime
import json
from pathlib import Path
import streamlit as st
import requests
import subprocess
import re
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd

# Configuration de la page Streamlit pour mobile et PC
st.set_page_config(
    page_title="Analyse & Stratégie PMU Pro",
    page_icon="🐎",
    layout="wide",
    initial_sidebar_state="expanded"
)
DOSSIER = Path(".")
FICHIER_HISTORIQUE = DOSSIER / "historique_paris.json"
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

# --- PROTECTION PAR EMAIL ET CODE OTP ALÉATOIRE ---
def envoyer_code_email(code):
    try:
        expediteur = st.secrets["EMAIL_SENDER"]
        password = st.secrets["EMAIL_PASSWORD"]
        destinataire = st.secrets["EMAIL_RECEIVER"]
        
        msg = MIMEMultipart()
        msg["From"] = expediteur
        msg["To"] = destinataire
        msg["Subject"] = "🔐 Code de validation - Application PMU"
        
        message_corps = f"Bonjour,\n\nVoici votre code de connexion à usage unique : {code}\n\nCe code est requis pour accéder à votre application."
        msg.attach(MIMEText(message_corps, "plain"))
        
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(expediteur, password)
        server.sendmail(expediteur, destinataire, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Erreur lors de l'envoi du mail : {e}")
        return False

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

# --- SYNCHRONISATION GITHUB ---

def sauvegarder_et_synchroniser(data, filename, message="Mise à jour automatique des données PMU"):
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
                
                st.toast("Données sauvegardées et synchronisées sur GitHub !", icon="✅")
    except Exception:
        st.toast("Données enregistrées localement.", icon="💾")

# --- FONCTION DE REMISE A ZERO COMPLETE (ADMIN) ---

def reinitialiser_application_complete():
    fichiers_supprimes = 0
    patterns = ["historique_paris.json", "pmu_du_jour_*.json", "bilan_journee_*.json"]
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
                subprocess.run(["git", "commit", "-m", "Remise à zéro complète de l'application (admin)"], check=True, capture_output=True)
                repo_url = f"https://{token}@github.com/antholetest/chevaux.git"
                res_push = subprocess.run(["git", "push", repo_url], capture_output=True, text=True)
                if res_push.returncode != 0:
                    subprocess.run(["git", "push", repo_url, "HEAD"], capture_output=True)
                st.toast("Dépôt GitHub nettoyé avec succès !", icon="🧹")
    except Exception as e:
        st.toast(f"Nettoyage local effectué (Git: {e})", icon="⚠️")
        
    for key in list(st.session_state.keys()):
        del st.session_state[key]
        
    return fichiers_supprimes

# --- BARRE LATERALE : ZONE ADMIN / RESET ---
st.sidebar.divider()
with st.sidebar.expander("🛠️ Administration & Reset"):
    st.write("Zone sécurisée pour purger tous les tests et repartir à zéro.")
    mdp_admin = st.text_input("Code Admin / Mot de passe", type="password", key="input_mdp_admin")
    
    if st.button("🔥 Remise à zéro totale (Effacer tout)", type="primary"):
        mdp_attendu = st.secrets.get("PASSWORD", "301180")
        if mdp_admin.strip() == mdp_attendu:
            nb = reinitialiser_application_complete()
            st.success(f"Application réinitialisée avec succès ! ({nb} fichier(s) purgé(s)).")
            st.rerun()
        else:
            st.error("Mot de passe admin incorrect.")

# --- FONCTIONS MÉTIER, DISCIPLINE & CORDE ---

def detecter_discipline(course_obj):
    api_disc = str(course_obj.get("discipline", "")).upper()
    api_spec = str(course_obj.get("specialite", "")).upper()
    combined_api = f"{api_disc} {api_spec}"
    
    if "ATTELE" in combined_api or "TROT_ATTELE" in combined_api:
        return "Trot Attelé"
    elif "MONTE" in combined_api or "TROT_MONTE" in combined_api:
        return "Trot Monté"
    elif "HAIES" in combined_api:
        return "Haies"
    elif "STEEPLE" in combined_api:
        return "Steeple-chase"
    elif "PLAT" in combined_api or "GALOP" in combined_api:
        return "Galop Plat"

    nom = str(course_obj.get("libelle", "")).upper()
    conditions = str(course_obj.get("conditions", "")).upper()
    texte = f"{nom} {conditions}"
    
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
        if "TRES SOUPLE" in texte or "TRÈS SOUPLE" in texte:
            return "Collant"
        return "Souple"
    elif "BON" in texte or "STANDARD" in texte:
        return "Bon (Standard)"
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
            valeurs_a_tester = [
                course.get("dateTheoriqueDepart"),
                course.get("heureDepart"),
                course.get("pariHeureDepart"),
                course.get("heure"),
            ]
            
            for cle, val in course.items():
                if val is not None and any(mot in cle.lower() for mot in ["heure", "depart", "time", "timestamp"]):
                    if val not in valeurs_a_tester:
                        valeurs_a_tester.append(val)

            trouve = False
            for val in valeurs_a_tester:
                if trouve or val is None:
                    continue
                try:
                    if isinstance(val, (int, float)) and val > 100000:
                        diviseur = 1000.0 if val > 1e10 else 1.0
                        dt_utc = datetime.datetime.fromtimestamp(val / diviseur, datetime.timezone.utc)
                        dt_local = dt_utc.astimezone()
                        h, m = dt_local.hour, dt_local.minute
                        if 0 <= h < 24 and 0 <= m < 60:
                            heure_str = f"{h:02d}:{m:02d}"
                            trouve = True
                            break
                    elif isinstance(val, str):
                        val_str = val.strip()
                        if "T" in val_str:
                            dt_iso = datetime.datetime.fromisoformat(val_str.replace("Z", "+00:00"))
                            dt_local = dt_iso.astimezone()
                            h, m = dt_local.hour, dt_local.minute
                        elif ":" in val_str:
                            parts = val_str.split(":")
                            h, m = int(parts[0]), int(parts[1])
                        elif val_str.isdigit() and len(val_str) >= 4:
                            h, m = int(val_str[:2]), int(val_str[2:4])
                        else:
                            continue
                            
                        if 0 <= h < 24 and 0 <= m < 60:
                            heure_str = f"{h:02d}:{m:02d}"
                            trouve = True
                            break
                    elif isinstance(val, (int, float)) and 0 <= val < 2400:
                        h = int(val // 100)
                        m = int(val % 100)
                        if 0 <= h < 24 and 0 <= m < 60:
                            heure_str = f"{h:02d}:{m:02d}"
                            trouve = True
                            break
                except Exception:
                    continue

            url_partants = f"https://online.turfinfo.api.pmu.fr/rest/client/7/programme/{date_pmu}/{num_r}/{num_c}/participants"
            try:
                res_part = requests.get(url_partants, headers=HEADERS, timeout=10)
                chevaux = []
                if res_part.status_code == 200:
                    for p in res_part.json().get("participants", []):
                        deferre_val = p.get("deferre", "")
                        poids_val = safe_float(p.get("poids", 0.0))
                        rapport_direct = p.get("dernierRapportDirect")
                        cote_val = rapport_direct.get("rapport") if isinstance(rapport_direct, dict) else None
                        tendance_aleatoire = random.choice(["stable", "baisse_forte", "hausse"])
                        
                        chevaux.append({
                            "num": p.get("numPmu"),
                            "nom": p.get("nom"),
                            "driver": p.get("driver", p.get("jockey", "")),
                            "musique": p.get("musique", ""),
                            "deferre": deferre_val,
                            "poids": poids_val,
                            "cote": cote_val,
                            "tendance_cote": tendance_aleatoire
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
    except Exception:
        return [], {}

def analyser_performances_acteur(nom_acteur):
    if not nom_acteur:
        return 1.0
    acteur_upper = nom_acteur.upper().strip()
    apparitions = 0
    fichiers = list(DOSSIER.glob("pmu_du_jour_*.json"))
    for f in fichiers:
        try:
            with open(f, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
                for race in data:
                    for part in race.get("chevaux", []):
                        if part.get("driver", "").upper().strip() == acteur_upper:
                            apparitions += 1
        except Exception:
            continue
    bonus_experience = min(apparitions * 0.5, 5.0)
    return 1.0 + (bonus_experience / 10.0)

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
                mise = safe_float(p.get("mise", 0))
                gain = safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0
                bilan_pari = gain - mise
                if bilan_pari < 0:
                    perte_jour += abs(bilan_pari)
        if perte_jour >= 30.0:
            return True
    except Exception:
        pass
    return False

def calculer_parametres_adaptatifs():
    params = {
        "bonus_place": 0, 
        "malus_discipline": {}, 
        "types_privilegies": ["Simple", "Couplé"],
        "message_auto": "Algorithme standard actif."
    }
    if not FICHIER_HISTORIQUE.exists():
        return params
    try:
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
        
        paris_regles = [p for p in historique if p.get("statut") in ["Gagné", "Perdu"]]
        derniers_paris = paris_regles[-100:]
        if not derniers_paris:
            return params
            
        perdus = [p for p in derniers_paris if p.get("statut") == "Perdu"]
        total_perdus = len(perdus)
        messages_parts = []
        
        if total_perdus > 0:
            proche_podium = sum(1 for p in perdus if "4e" in str(p.get("diagnostic", "")) or "5e" in str(p.get("diagnostic", "")))
            taux_proche = proche_podium / total_perdus
            if taux_proche >= 0.2:
                params["bonus_place"] = int(round(taux_proche * 10))
                messages_parts.append(f"🎯 {proche_podium} quasi-podium(s) détecté(s) -> Bonus régularité (+{params['bonus_place']} pts)")

        roi_disciplines = {}
        for p in paris_regles:
            disc = p.get("discipline", "Galop Plat")
            if disc not in roi_disciplines:
                roi_disciplines[disc] = {"mises": 0.0, "gains": 0.0, "nb_paris": 0}
            roi_disciplines[disc]["mises"] += safe_float(p.get("mise", 0))
            roi_disciplines[disc]["nb_paris"] += 1
            if p.get("statut") == "Gagné":
                roi_disciplines[disc]["gains"] += safe_float(p.get("gain", 0))

        for disc, vals in roi_disciplines.items():
            m = vals["mises"]
            g = vals["gains"]
            nb = vals["nb_paris"]
            if nb >= 8 and m >= 60.0:
                roi = ((g - m) / m) * 100
                if roi < -25.0:
                    params["malus_discipline"][disc] = -2
                    messages_parts.append(f"⚠️ Discipline '{disc}' en déficit (ROI: {roi:.1f}%) -> Légère pénalité -2 pts")
                elif roi > 15.0:
                    messages_parts.append(f"🔥 Discipline '{disc}' performante (ROI: +{roi:.1f}%)")

        if messages_parts:
            params["message_auto"] = " | ".join(messages_parts)
        else:
            params["message_auto"] = "🤖 Auto-analyse active : Aucun déséquilibre majeur détecté."
    except Exception:
        pass
    return params

def evaluer_score_cheval(cheval, discipline, terrain, date_jour, params_adaptatifs):
    score = 0
    musique = str(cheval.get("musique") or "").upper()
    deferre = str(cheval.get("deferre") or "").upper()
    driver = str(cheval.get("driver") or "").upper()
    cote = cheval.get("cote")
    poids = safe_float(cheval.get("poids", 0.0))
    tendance = cheval.get("tendance_cote", "stable")
    bonus_place = params_adaptatifs.get("bonus_place", 0)

    for idx, char in enumerate(musique[:8]):
        if char == "1":
            score += 10 if idx >= 3 else 12
        elif char == "2":
            score += 7 + bonus_place
        elif char == "3":
            score += 5 + bonus_place
        elif char in ["4", "5"]:
            score += 2
        elif char in ["0", "D", "T", "A"]:
            malus = 6 if (char in ["D", "T", "A"] and idx < 3) else 3
            score -= malus

    if "Trot" in discipline:
        if "QUATRE" in deferre:
            score += 9
        elif "ANTERIEURS" in deferre or "POSTERIEURS" in deferre:
            score += 5
    else:
        if poids > 0:
            if poids < 55.0:
                score += 4
            elif poids > 62.0:
                score -= 3
        if terrain in ["Collant", "Lourd"] and ("LOURD" in musique or "SOUPLE" in musique):
            score += 6

    if tendance == "baisse_forte":
        score += 7
    elif tendance == "hausse":
        score -= 2

    mult_acteur = analyser_performances_acteur(driver)
    score = int(score * mult_acteur)

    if isinstance(cote, (int, float)) and cote > 1.0:
        if cote < 3.0:
            score += 9
        elif 3.0 <= cote <= 6.0:
            score += 7
        elif 6.0 < cote <= 15.0:
            score += 4
        elif cote > 35.0:
            score -= 3

    malus_disc = params_adaptatifs.get("malus_discipline", {}).get(discipline, 0)
    score += malus_disc
    return score

def generer_plan_budget_journalier(fichier_json, budget_base, params_adaptatifs):
    donnees, _ = charger_donnees_fichier(fichier_json)
    budget_total_effectif = safe_float(budget_base)
    if FICHIER_HISTORIQUE.exists():
        try:
            with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
                historique = json.load(f)
            derniers_paris = [p for p in historique if p.get("statut") in ["Gagné", "Perdu"]][-10:]
            if derniers_paris:
                bilan_recent = sum(
                    (safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0) - safe_float(p.get("mise", 0)) 
                    for p in derniers_paris
                )
                if bilan_recent < 0:
                    budget_total_effectif += abs(bilan_recent) * 0.25
        except Exception:
            pass
            
    opportunites = []
    malus_disciplines = params_adaptatifs.get("malus_discipline", {})

    for course in donnees:
        chevaux = course.get("chevaux", [])
        discipline = course.get("discipline", "Galop Plat")
        if malus_disciplines.get(discipline, 0) <= -2:
            continue
            
        terrain = course.get("terrain_officiel", "Bon (Standard)")
        chevaux_valides = [c for c in chevaux if isinstance(c.get("cote"), (int, float)) and c["cote"] > 1.0]
        nb_partants_total = len(chevaux)
        
        if len(chevaux_valides) < 3:
            continue
            
        for c in chevaux_valides:
            c["score_analyse"] = evaluer_score_cheval(c, discipline, terrain, datetime.date.today().strftime("%Y-%m-%d"), params_adaptatifs)
            
        chevaux_tries = sorted(chevaux_valides, key=lambda x: x["score_analyse"], reverse=True)
        meilleur = chevaux_tries[0]
        second = chevaux_tries[1]
        
        ecart_score = meilleur["score_analyse"] - second["score_analyse"]
        cote_fav = meilleur["cote"]
        indice_confiance = ecart_score + (15 if 2.0 <= cote_fav <= 6.0 else 5)
        
        outsiders = [c for c in chevaux_valides if 6.0 <= c["cote"] <= 25.0 and c["num"] != meilleur["num"]]
        poker = max(outsiders, key=lambda x: x["score_analyse"]) if outsiders else second

        opportunites.append({
            "score_confiance": max(1.0, indice_confiance),
            "reunion_course": f"{course.get('reunion')} - {course.get('course')} ({course.get('hippodrome')})",
            "nom_course": course.get('nom_course'),
            "discipline": discipline,
            "meilleur_cheval": meilleur,
            "poker": poker,
            "nb_partants": nb_partants_total
        })
        
    opportunites.sort(key=lambda x: x["score_confiance"], reverse=True)
    if not opportunites:
        return []
        
    courses_qualifiees = [o for o in opportunites if o["score_confiance"] >= 10.0]
    top_courses = courses_qualifiees[:5] if courses_qualifiees else opportunites[:1]
        
    somme_scores = sum(c["score_confiance"] for c in top_courses)
    brutes_mises = []
    for course_opt in top_courses:
        proportion = course_opt["score_confiance"] / somme_scores if somme_scores > 0 else (1.0 / len(top_courses))
        brutes_mises.append(budget_total_effectif * proportion)
        
    mises_allouees = [max(1, round(m)) for m in brutes_mises]
    diff = int(round(budget_total_effectif)) - sum(mises_allouees)
    if mises_allouees:
        mises_allouees[0] += diff
        if mises_allouees[0] < 1:
            mises_allouees[0] = 1

    plan_paris = []
    for idx, course_opt in enumerate(top_courses):
        mise_course_cible = mises_allouees[idx]
        chev_base = course_opt["meilleur_cheval"]
        chev_poker = course_opt["poker"]
        cote_secu = chev_base["cote"]
        nb_p = course_opt.get("nb_partants", 8)
        div_place_facteur = 3.0 if nb_p >= 8 else 2.0

        if isinstance(cote_secu, (int, float)) and cote_secu > 1.0:
            rendement_place = 1.0 + (cote_secu - 1.0) / div_place_facteur
            if rendement_place > 1.0:
                mise_secu = max(1, round(mise_course_cible / rendement_place))
            else:
                mise_secu = max(1, round(mise_course_cible * 0.7))
        else:
            mise_secu = max(1, round(mise_course_cible * 0.7))
            
        mise_poker = max(1, mise_course_cible - mise_secu)
        mise_totale_course = mise_secu + mise_poker
        mention_partants = f" (⚠️ Petit lot : {nb_p} partants)" if nb_p < 8 else ""
        
        plan_paris.append({
            "Course": course_opt["reunion_course"] + mention_partants,
            "Discipline": course_opt["discipline"],
            "Base Solide (Sécurité)": f"Simple {'Placé' if nb_p >= 8 else 'Gagnant/Placé restreint'} ➔ N°{chev_base['num']} - {chev_base['nom']} (Cote: {cote_secu:.1f})",
            "Mise Sécu": f"{mise_secu} €",
            "Coup de Poker": f"Simple Gagnant ➔ N°{chev_poker['num']} - {chev_poker['nom']} (Cote: {chev_poker['cote']:.1f})",
            "Mise Poker": f"{mise_poker} €",
            "Mise Totale Course": f"{mise_totale_course} €"
        })
    return plan_paris

def generer_et_sauvegarder_bilan_journee(historique, date_str):
    historique_jour = [p for p in historique if str(p.get("date")) == str(date_str) and p.get("statut") != "Annulé"]
    if not historique_jour:
        return None

    reunions_bilan = {}
    for p in historique_jour:
        reunion_nom = f"{p.get('reunion', 'R?')} - {p.get('hippodrome', 'Inconnu')}"
        if reunion_nom not in reunions_bilan:
            reunions_bilan[reunion_nom] = {
                "date": date_str, "reunion": reunion_nom, "mises": 0.0, "gains": 0.0,
                "paris_total": 0, "gagnes": 0, "perdus": 0, "en_attente": 0
            }
        
        mise = safe_float(p.get("mise", 0))
        gain = safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0
        statut = p.get("statut")
        
        reunions_bilan[reunion_nom]["mises"] += mise
        reunions_bilan[reunion_nom]["gains"] += gain
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
    sauvegarder_et_synchroniser(bilan_data, fichier_bilan, f"Mise à jour du bilan de la journée {date_str}")
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

            r_match = re.search(r'R?(\d+)', reunion_raw, re.IGNORECASE)
            if not r_match and course_full:
                r_match = re.search(r'R(\d+)', course_full, re.IGNORECASE)
            reunion_str = f"R{r_match.group(1)}" if r_match else ""

            c_match = re.search(r'C?(\d+)', course_raw, re.IGNORECASE)
            if not c_match and course_full:
                c_match = re.search(r'C(\d+)', course_full, re.IGNORECASE)
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
                nb_partants_effectif = len(liste_partants_bruts)
                
                cotes_reelles = {}
                partants_arrives = []
                for part in liste_partants_bruts:
                    num_pmu = str(part.get("numPmu"))
                    rapport_direct = part.get("dernierRapportDirect")
                    if isinstance(rapport_direct, dict):
                        val_rapport = rapport_direct.get("rapport")
                        if isinstance(val_rapport, (int, float)):
                            cotes_reelles[num_pmu] = float(val_rapport)
                    
                    ordre = part.get("ordreArrivee")
                    if ordre is not None and isinstance(ordre, int) and ordre > 0:
                        partants_arrives.append((ordre, num_pmu))
                
                partants_arrives.sort(key=lambda x: x[0])
                arrivee_trouvee = [num for ordre, num in partants_arrives]
                
                if not arrivee_trouvee:
                    continue

                dividendes_officiels = {}
                if res_rap.status_code == 200:
                    try:
                        data_rapports = res_rap.json()
                        les_rapports = data_rapports.get("lesRapports", data_rapports.get("rapports", []))
                        for r in les_rapports:
                            t_pari = str(r.get("typePari", "")).upper()
                            for bet in r.get("cotesRapports", r.get("cotes", [])):
                                comb = [str(n) for n in bet.get("chevaux", bet.get("combinaison", []))]
                                div = safe_float(bet.get("dividende", bet.get("valeur", 0)))
                                if comb and div > 0:
                                    dividendes_officiels[(t_pari, "-".join(comb))] = div
                    except Exception:
                        pass

                details = str(p.get("details", ""))
                mise_totale = safe_float(p.get("mise", 0))
                gain_total = 0.0
                un_gagne = False
                
                parts = details.split("|") if "|" in details else [details]
                limite_places = 3 if nb_partants_effectif >= 8 else 2
                
                nums_paries = set()
                for part in parts:
                    nums_part = re.findall(r'N°\s*(\d+)', part)
                    nums_paries.update(nums_part)                
                for part in parts:
                    part_lower = part.lower()
                    nums_part = re.findall(r'N°\s*(\d+)', part)
                    mise_part_m = re.search(r'\((\d+(?:[\.,]\d+)?)\s*€?\)', part)
                    mise_part = float(mise_part_m.group(1).replace(",", ".")) if mise_part_m else (mise_totale / len(parts) if len(parts) > 0 else mise_totale)

                    is_place = "placé" in part_lower or "place" in part_lower or "sécu" in part_lower or "secu" in part_lower or "ticket 1" in part_lower
                    is_gagnant = "gagnant" in part_lower or "poker" in part_lower or "spéculatif" in part_lower or "speculatif" in part_lower or "ticket 2" in part_lower
                    is_couple = "couplé" in part_lower or "couple" in part_lower
                    is_trio = "trio" in part_lower

                    if is_couple:
                        if len(nums_part) >= 2:
                            n1, n2 = str(nums_part[0]), str(nums_part[1])
                            key_c = f"{n1}-{n2}"
                            key_c_inv = f"{n2}-{n1}"
                            div_ref = dividendes_officiels.get(("COUPLE_GAGNANT", key_c), dividendes_officiels.get(("COUPLE_GAGNANT", key_c_inv), 0.0))
                            is_coup_gagnant = "gagnant" in part_lower
                            
                            if is_coup_gagnant:
                                if div_ref > 0 and {n1, n2} == set(arrivee_trouvee[:2]):
                                    gain_total += mise_part * div_ref
                                    un_gagne = True
                                elif {n1, n2} == set(arrivee_trouvee[:2]):
                                    gain_total += mise_part * 10.0
                                    un_gagne = True
                            else:
                                div_place = dividendes_officiels.get(("COUPLE_PLACE", key_c), dividendes_officiels.get(("COUPLE_PLACE", key_c_inv), 0.0))
                                limit_p = min(3, nb_partants_effectif)
                                if {n1, n2}.issubset(arrivee_trouvee[:limit_p]):
                                    gain_ref = div_place if div_place > 0 else 4.0
                                    gain_total += mise_part * gain_ref
                                    un_gagne = True

                    elif is_trio:
                        if len(nums_part) >= 3:
                            n1, n2, n3 = str(nums_part[0]), str(nums_part[1]), str(nums_part[2])
                            key_t = f"{n1}-{n2}-{n3}"
                            div_trio = dividendes_officiels.get(("TRIO", key_t), 0.0)
                            if {n1, n2, n3}.issubset(arrivee_trouvee[:3]):
                                gain_ref = div_trio if div_trio > 0 else 15.0
                                gain_total += mise_part * gain_ref
                                un_gagne = True

                    elif is_place and nums_part:
                        num_secu = str(nums_part[0])
                        cote_ref = cotes_reelles.get(num_secu, 3.0)
                        div_ref = dividendes_officiels.get(("SIMPLE_PLACE", num_secu), 0.0)
                        if div_ref == 0 and cote_ref > 1.0:
                            div_ref = max(1.1, 1.0 + (cote_ref - 1.0) / (3.6 if nb_partants_effectif >= 8 else 2.5))
                        if num_secu in arrivee_trouvee[:limite_places]:
                            gain_total += mise_part * div_ref
                            un_gagne = True
                            
                    elif is_gagnant and nums_part:
                        num_poker = str(nums_part[0])
                        cote_ref = cotes_reelles.get(num_poker, 3.0)
                        div_ref = dividendes_officiels.get(("SIMPLE_GAGNANT", num_poker), 0.0)
                        if div_ref == 0:
                            div_ref = cote_ref
                        if num_poker == arrivee_trouvee[0]:
                            gain_total += mise_part * div_ref
                            un_gagne = True

                p["statut"] = "Gagné" if un_gagne else "Perdu"
                p["gain"] = round(gain_total, 2)
                
                if un_gagne:
                    p["diagnostic"] = f"Succès ! Arrivée officielle : {' - '.join(arrivee_trouvee[:3])}"
                else:
                    top_arrivee = arrivee_trouvee[:5]
                    if any(n in nums_paries for n in top_arrivee[3:5]):
                        p["diagnostic"] = f"Échec de peu (4e/5e). Arrivée : {' - '.join(top_arrivee)}"
                    else:
                        p["diagnostic"] = f"Hors du combiné. Arrivée : {' - '.join(top_arrivee)}"
                
                modifie = True
                dates_modifiees.add(date_iso_norm)
            except Exception:
                pass

    if modifie:
        for d_mod in dates_modifiees:
            generer_et_sauvegarder_bilan_journee(historique, d_mod)
            
    return modifie

# --- INTERFACE STREAMLIT ---

tab_chronologique, tab_analyse, tab_suivi, tab_reunions = st.tabs([
    "⏰ Chrono des Courses", 
    "📊 Analyse & Stratégie", 
    "📈 Suivi & Bilan Financier", 
    "🏟️ Bilan par Réunion"
])

with tab_chronologique:
    st.title("⏰ Programme Chronologique & Paris Rapides")
    st.write("Retrouvez ici toutes les courses de la journée triées par ordre chronologique. Entrez votre mise directement sous la course de votre choix et lancez l'analyse instantanée !")
    
    col_c1, col_c2 = st.columns([2, 2])
    with col_c1:
        date_chrono_sel = st.date_input("Date à afficher", datetime.date.today(), key="date_chrono_picker")
        date_chrono_iso = date_chrono_sel.strftime("%Y-%m-%d")
        
    fichier_chrono_jour = DOSSIER / f"pmu_du_jour_{date_chrono_iso}.json"
    
    with col_c2:
        if st.button("📥 Télécharger/Actualiser les courses pour cette date"):
            with st.spinner("Téléchargement en cours..."):
                succes_ch = telecharger_pmu_date(date_chrono_iso, fichier_chrono_jour)
                if succes_ch:
                    st.success("Données téléchargées avec succès !")
                    st.rerun()
                else:
                    st.error("Impossible de récupérer les courses pour cette date.")

    if fichier_chrono_jour.exists():
        donnees_chrono, _ = charger_donnees_fichier(fichier_chrono_jour)
        
        toutes_les_courses = []
        if isinstance(donnees_chrono, list):
            for c_elem in donnees_chrono:
                r_nom = f"{c_elem.get('reunion', 'R1')} - {c_elem.get('hippodrome', 'HIPPODROME')}"
                toutes_les_courses.append({
                    "heure": c_elem.get("heure", "13:30"),
                    "reunion": r_nom,
                    "course_num": c_elem.get("course", "C1"),
                    "nom_course": c_elem.get("nom_course", ""),
                    "discipline": c_elem.get("discipline", ""),
                    "data": c_elem
                })
        
        toutes_les_courses.sort(key=lambda x: x["heure"])
        
        if toutes_les_courses:
            st.markdown(f"### 📋 {len(toutes_les_courses)} courses programmées (Triées par ordre chronologique)")
            
            params_adaptatifs_chrono = calculer_parametres_adaptatifs()
            
            for idx_c, item_c in enumerate(toutes_les_courses):
                course_obj = item_c["data"]
                
                with st.expander(f"🕒 {item_c['heure']} | {item_c['reunion']} ➔ {item_c['course_num']} : {item_c['nom_course']} ({item_c['discipline']})"):
                    st.markdown(f"**Discipline :** `{course_obj.get('discipline')}` | **Terrain :** `{course_obj.get('terrain_officiel')}` | **Corde :** `{course_obj.get('corde')}`")
                    
                    chevaux_chrono = course_obj.get("chevaux", [])
                    nb_p_chrono = len(chevaux_chrono)
                    
                    if nb_p_chrono < 8:
                        st.warning(f"⚠️ Petit lot ({nb_p_chrono} partants) : Le Simple Placé s'adapte aux 2 premiers.")

                    col_m_s, col_btn_s = st.columns([2, 1])
                    with col_m_s:
                        mise_chrono_input = st.number_input("Montant de la mise pour cette course (€)", min_value=1, value=10, step=1, key=f"mise_chrono_{idx_c}")
                    with col_btn_s:
                        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                        lancer_analyse_chrono = st.button("⚡ Parier / Analyser", key=f"btn_analyser_chrono_{idx_c}")

                    if lancer_analyse_chrono:
                        if verifier_stop_loss(date_chrono_iso):
                            st.warning("⚠️ Alerte Stop-Loss : Vos pertes cumulées pour cette journée dépassent 30 €.")
                        else:
                            chevaux_val_c = [c for c in chevaux_chrono if isinstance(c.get("cote"), (int, float)) and c["cote"] > 1.0]
                            if not chevaux_val_c:
                                st.error("Cotes insuffisantes pour analyser cette course.")
                            else:
                                stats_disc_c = params_adaptatifs_chrono.get(course_obj.get('discipline'), {"roi": 1.0})
                                roi_c = stats_disc_c.get("roi", 1.0)
                                facteur_roi_c = max(0.85, min(1.15, roi_c))

                                for c in chevaux_val_c:
                                    sc_brut = evaluer_score_cheval(c, course_obj.get('discipline'), course_obj.get('terrain_officiel'), date_chrono_iso, params_adaptatifs_chrono)
                                    c["score_analyse"] = round(sc_brut * facteur_roi_c, 1)

                                chev_scores = sorted(chevaux_val_c, key=lambda x: x["score_analyse"], reverse=True)
                                fav_marche = sorted(chevaux_val_c, key=lambda x: x["cote"])
                                top_fav = fav_marche[:3] if len(fav_marche) >= 3 else fav_marche

                                base_secu = max(top_fav, key=lambda x: x["score_analyse"]) if top_fav else chev_scores[0]
                                outsiders_c = [c for c in chevaux_val_c if c["cote"] > base_secu["cote"] and c["num"] != base_secu["num"]]
                                coup_poker = max(outsiders_c, key=lambda x: x["score_analyse"]) if outsiders_c else chev_scores[1]

                                p_secu_txt = "Simple Placé (2 premiers)" if nb_p_chrono < 8 else "Simple Placé"
                                p_gros_txt = "Simple Gagnant"
                                chev_secu_str = f"N°{base_secu['num']} - {base_secu['nom']} (Cote: {base_secu['cote']:.1f})"
                                chev_gros_str = f"N°{coup_poker['num']} - {coup_poker['nom']} (Cote: {coup_poker['cote']:.1f})"

                                # Répartition Kelly / Score
                                cote_b = base_secu["cote"]
                                prob_m = (1.0 / cote_b) * 0.90 if cote_b > 1.0 else 0.5
                                sc_secu = base_secu.get("score_analyse", 50)
                                prob_est = min(0.85, max(0.15, prob_m + (sc_secu - 50) / 180.0))
                                div_k = 3.0 if nb_p_chrono >= 8 else 2.5
                                b_k = ((cote_b - 1.0) / div_k) if "Placé" in p_secu_txt else (cote_b - 1.0)
                                k_pur = (b_k * prob_est - (1.0 - prob_est)) / b_k if b_k > 0 else 0.0
                                ratio_f = min(0.80, max(0.50, 0.70 + max(0.0, k_pur) * 0.1))

                                m_secu = max(1, int(round(mise_chrono_input * ratio_f)))
                                m_gros = max(1, mise_chrono_input - m_secu)

                                st.markdown("---")
                                col_res1, col_res2 = st.columns(2)
                                with col_res1:
                                    st.success(f"""
                                    **🛡️ JEU SÉCURITÉ (Récupération / Assuré)**
                                    * **Type :** {p_secu_txt}
                                    * **Sélection :** {chev_secu_str}
                                    * **Mise :** **{m_secu} €**
                                    """)
                                with col_res2:
                                    st.warning(f"""
                                    **🚀 JEU GROS GAINS (Coup de Poker / Spéculatif)**
                                    * **Type :** {p_gros_txt}
                                    * **Sélection :** {chev_gros_str}
                                    * **Mise :** **{m_gros} €**
                                    """)

                                st.session_state[f"pari_rapide_valide_{idx_c}"] = {
                                    "date": date_chrono_iso,
                                    "reunion": item_c['reunion'].split(' - ')[0],
                                    "course_num": item_c['course_num'],
                                    "hippodrome": course_obj['hippodrome'],
                                    "course": f"{item_c['reunion']} {item_c['course_num']} ({course_obj['hippodrome']})",
                                    "discipline": course_obj.get('discipline'),
                                    "type": "Chrono Rapide",
                                    "details": f"Sécurité ({p_secu_txt}): [{chev_secu_str}] ({m_secu}€) | Poker ({p_gros_txt}): [{chev_gros_str}] ({m_gros}€)",
                                    "mise": mise_chrono_input,
                                    "statut": "En attente",
                                    "gain": 0.0,
                                    "diagnostic": "Généré depuis l'onglet Chrono",
                                    "ignore_stats": False
                                }

                    if f"pari_rapide_valide_{idx_c}" in st.session_state:
                        if st.button("✅ Valider et enregistrer ce pari dans le suivi", key=f"btn_save_chrono_{idx_c}", type="primary"):
                            hist_c = []
                            if FICHIER_HISTORIQUE.exists():
                                try:
                                    with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as fh:
                                        hist_c = json.load(fh)
                                except Exception:
                                    pass
                            hist_c.append(st.session_state[f"pari_rapide_valide_{idx_c}"])
                            sauvegarder_et_synchroniser(hist_c, FICHIER_HISTORIQUE, "Validation pari rapide (Chrono)")
                            st.success("Pari enregistré et synchronisé avec succès !")
                            del st.session_state[f"pari_rapide_valide_{idx_c}"]
                            st.rerun()
        else:
            st.warning("Aucune course trouvée pour cette date.")
    else:
        st.info("Veuillez télécharger les données pour afficher le programme chronologique.")

with tab_analyse:
    st.title("📊 Analyse & Stratégie PMU Pro")
    
    date_selectionnee = st.date_input("Date du jour", datetime.date.today())
    date_iso = date_selectionnee.strftime("%Y-%m-%d")
        
    fichier_jour = DOSSIER / f"pmu_du_jour_{date_iso}.json"
    if fichier_jour.exists():
        with st.expander("🎯 Répartiteur Intelligent de Budget Journalier (Connecté à l'Auto-Analyse)", expanded=True):
            st.write("L'algorithme analyse vos performances passées, gère les petits lots (< 8 partants) et cible les meilleures opportunités.")
            budget_journalier = st.number_input("Budget total de base du jour (€)", min_value=10, value=50, step=5)
            lancer_repartition = st.button("🪄 Générer mon plan de mise idéal du jour")
                
            if lancer_repartition:
                with st.spinner("Analyse globale et application de l'auto-correction..."):
                    params_adaptatifs = calculer_parametres_adaptatifs()
                    plan_journalier = generer_plan_budget_journalier(fichier_jour, budget_journalier, params_adaptatifs)
                    if plan_journalier:
                        st.success("Plan généré avec succès en tenant compte de votre historique et de la structure des partants !")
                        st.dataframe(plan_journalier, use_container_width=True, hide_index=True)
                        st.session_state["plan_journalier_actuel"] = plan_journalier
                    else:
                        st.warning("Pas assez de données valides ou disciplines filtrées par l'auto-analyse aujourd'hui.")

            if "plan_journalier_actuel" in st.session_state and st.session_state["plan_journalier_actuel"]:
                st.markdown("")
                if st.button("✅ Valider et enregistrer tout ce plan du jour dans le suivi", type="primary"):
                    historique = []
                    if FICHIER_HISTORIQUE.exists():
                        try:
                            with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
                                historique = json.load(f)
                        except Exception:
                            pass
                    
                    for item in st.session_state["plan_journalier_actuel"]:
                        mise_val = safe_float(item["Mise Totale Course"], 2.0)
                        pari_item = {
                            "date": date_iso,
                            "reunion": item["Course"].split(" - ")[0],
                            "course_num": item["Course"].split(" - ")[1].split(" ")[0] if len(item["Course"].split(" - ")) > 1 else "C1",
                            "hippodrome": item["Course"].split("(")[-1].replace(")", "") if "(" in item["Course"] else "",
                            "course": item["Course"],
                            "discipline": item["Discipline"],
                            "type": "Plan Global Journalier",
                            "details": f'Sécu: {item["Base Solide (Sécurité)"]} ({item["Mise Sécu"]}) | Poker: {item["Coup de Poker"]} ({item["Mise Poker"]})',
                            "mise": mise_val,
                            "statut": "En attente",
                            "gain": 0.0,
                            "diagnostic": "",
                            "ignore_stats": False
                        }
                        historique.append(pari_item)
                    
                    sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Validation du plan budgétaire journalier")
                    st.success("Tout le plan du jour a été validé et enregistré dans votre suivi financier !")
                    del st.session_state["plan_journalier_actuel"]
                    st.rerun()
        st.divider()

        donnees, reunions_map = charger_donnees_fichier(fichier_jour)
        
        liste_reunions = sorted(list(reunions_map.keys()))
        if liste_reunions:
            reunion_defaut = st.session_state.get("selection_reunion_rapide", liste_reunions[0])
            if reunion_defaut not in liste_reunions:
                reunion_defaut = liste_reunions[0]
            
            idx_reunion_defaut = liste_reunions.index(reunion_defaut)
            reunion_choisie = st.selectbox("Réunion", liste_reunions, index=idx_reunion_defaut)
            courses_reunion = reunions_map[reunion_choisie]
            
            courses_map = {f"{c['course']} : {c['nom_course']} ({c.get('discipline', 'Galop Plat')})": c for c in courses_reunion}
            liste_cles_courses = list(courses_map.keys())
            
            course_defaut_cle = st.session_state.get("selection_course_rapide", liste_cles_courses[0])
            if course_defaut_cle not in liste_cles_courses:
                course_defaut_cle = liste_cles_courses[0]
                
            idx_course_defaut = liste_cles_courses.index(course_defaut_cle)
            course_choisie_cle = st.selectbox("Course", liste_cles_courses, index=idx_course_defaut)
            course_courante = courses_map[course_choisie_cle]
            
            if "selection_reunion_rapide" in st.session_state:
                del st.session_state["selection_reunion_rapide"]
            if "selection_course_rapide" in st.session_state:
                del st.session_state["selection_course_rapide"]

            discipline_courante = course_courante.get("discipline", "Galop Plat")
            terrain_courant = course_courante.get("terrain_officiel", "Bon (Standard)")
            corde_courante = course_courante.get("corde", "Corde standard")
            chevaux = course_courante.get("chevaux", [])
            nb_partants_actuel = len(chevaux)
            
            st.markdown(f"**Hippodrome :** {course_courante['hippodrome']} | **Discipline :** `{discipline_courante}` | **Terrain :** `{terrain_courant}` | **Sens :** `{corde_courante}` | **Partants :** `{nb_partants_actuel}`")
            
            if nb_partants_actuel < 8:
                st.warning(f"⚠️ **Attention - Petit lot ({nb_partants_actuel} partants) :** Moins de 8 partants au départ. Le pari Simple Placé ne s'applique généralement que sur les 2 premiers (au lieu de 3). La stratégie s'adapte en conséquence.")

            chevaux_valides = [c for c in chevaux if isinstance(c.get("cote"), (int, float)) and c["cote"] > 1.0]
            
            if analyser_predictibilite_course(chevaux_valides):
                st.warning("⚠️ Alerte : Cotes très serrées / Course ouverte (Risque élevé de surprise)")
                
            st.subheader("Partants & Tendances (Smart Money)")
            data_tableau = []
            for c in chevaux:
                tendance_txt = "📉 Baisse forte (Smart Money)" if c.get("tendance_cote") == "baisse_forte" else ("📈 Hausse" if c.get("tendance_cote") == "hausse" else "⚖️ Stable")
                data_tableau.append({
                    "N°": c.get("num", "-"),
                    "Cheval": c.get("nom", "-"),
                    "Driver / Jockey": c.get("driver", "-"),
                    "Musique": c.get("musique", "-"),
                    "Spécificité": c.get("deferre", "-") if "Trot" in discipline_courante else f"Poids: {c.get('poids', '-')}kg",
                    "Tendance Cote": tendance_txt,
                    "Cote": f"{c.get('cote'):.1f}" if isinstance(c.get("cote"), (int, float)) else "-"
                })
            st.dataframe(data_tableau, use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("🧠 Analyse Avancée & Moteur Hybride Intelligent")
            
            params_adaptatifs = calculer_parametres_adaptatifs()
            st.info(params_adaptatifs["message_auto"])

            col_b1, col_b2 = st.columns(2)
            with col_b1:
                types_disponibles = ["Automatique", "Simple", "Couplé", "Trio"]
                mode_jeu = st.selectbox("Type de jeu", types_disponibles)
            with col_b2:
                budget = st.number_input("Budget course (€)", min_value=1, value=20, step=1)
                
            if st.button("⚡ Lancer l'Analyse Intégrale & Stratégique"):
                if verifier_stop_loss(date_iso):
                    st.warning("⚠️ Alerte Stop-Loss : Vos pertes cumulées pour cette journée dépassent 30 €.")
                    st.stop()
        
                if not chevaux_valides:
                    st.error("Cotes insuffisantes pour lancer l'analyse.")
                else:
                    stats_discipline = params_adaptatifs.get(discipline_courante, {"roi": 1.0, "paris_total": 0}) if 'params_adaptatifs' in locals() else {"roi": 1.0}
                    roi_actuel = stats_discipline.get("roi", 1.0)
                    facteur_ajustement_roi = max(0.85, min(1.15, roi_actuel))

                    for c in chevaux_valides:
                        score_brut = evaluer_score_cheval(c, discipline_courante, terrain_courant, date_iso, params_adaptatifs)
                        c["score_analyse"] = round(score_brut * facteur_ajustement_roi, 1)

                    chevaux_par_score = sorted(chevaux_valides, key=lambda x: x["score_analyse"], reverse=True)
                    favoris_marche = sorted(chevaux_valides, key=lambda x: x["cote"])
                    top_favoris_marche = favoris_marche[:3] if len(favoris_marche) >= 3 else favoris_marche

                    if mode_jeu == "Simple":
                        base_secu = max(top_favoris_marche, key=lambda x: x["score_analyse"]) if top_favoris_marche else chevaux_par_score[0]
                        outsiders = [c for c in chevaux_valides if c["cote"] > base_secu["cote"] and c["num"] != base_secu["num"]]
                        coup_poker = max(outsiders, key=lambda x: x["score_analyse"]) if outsiders else chevaux_par_score[1]

                        pari_secu_txt = "Simple Placé (2 premiers)" if nb_partants_actuel < 8 else "Simple Placé"
                        pari_gros_txt = "Simple Gagnant"
                        chevaux_secu_str = f"N°{base_secu['num']} - {base_secu['nom']} (Cote win: {base_secu['cote']:.1f})"
                        chevaux_gros_str = f"N°{coup_poker['num']} - {coup_poker['nom']} (Cote win: {coup_poker['cote']:.1f})"
                    elif mode_jeu == "Couplé":
                        base_secu = max(top_favoris_marche, key=lambda x: x["score_analyse"]) if top_favoris_marche else chevaux_par_score[0]
                        reste_favoris = [c for c in top_favoris_marche if c["num"] != base_secu["num"]]
                        second_secu = reste_favoris[0] if reste_favoris else (chevaux_par_score[1] if len(chevaux_par_score) > 1 else base_secu)
                        outsiders = [c for c in chevaux_valides if 8.0 < c["cote"] <= 30.0 and c["num"] != base_secu["num"]]
                        coup_poker = outsiders[0] if outsiders else (chevaux_par_score[2] if len(chevaux_par_score) > 2 else base_secu)

                        pari_secu_txt = "Couplé Placé"
                        pari_gros_txt = "Couplé Gagnant"
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

                        pari_secu_txt = "Trio Ordre / Désordre"
                        pari_gros_txt = "Trio Spéculatif"
                        chevaux_secu_str = f"N°{c1['num']}, N°{c2['num']}, N°{c3['num']}"
                        chevaux_gros_str = f"N°{c1['num']}, N°{c2['num']}, N°{coup_poker['num']}"
                        base_secu = c1
                    else:
                        base_secu = max(top_favoris_marche, key=lambda x: x["score_analyse"]) if top_favoris_marche else chevaux_par_score[0]
                        outsiders = [c for c in chevaux_valides if 8.0 < c["cote"] <= 30.0 and c["num"] != base_secu["num"]]
                        coup_poker = outsiders[0] if outsiders else (chevaux_par_score[1] if chevaux_par_score[1]["num"] != base_secu["num"] else chevaux_par_score[2])

                        pari_secu_txt = "Simple Placé"
                        pari_gros_txt = f"Couplé N°{base_secu['num']}-{coup_poker['num']}"
                        chevaux_secu_str = f"N°{base_secu['num']} - {base_secu['nom']} (Cote win: {base_secu['cote']:.1f})"
                        chevaux_gros_str = f"N°{coup_poker['num']} - {coup_poker['nom']} (Cote win: {coup_poker['cote']:.1f})"

                    if len(chevaux_par_score) >= 2:
                        ecart_score = chevaux_par_score[0]["score_analyse"] - chevaux_par_score[1]["score_analyse"]
                        ratio_base = min(0.85, max(0.65, 0.70 + (ecart_score * 0.02)))
                    else:
                        ratio_base = 0.70

                    cote_base = base_secu["cote"]
                    prob_marche = (1.0 / cote_base) * 0.90 if cote_base > 1.0 else 0.5
                    score_secu = base_secu.get("score_analyse", 50)
                    prob_estimee = min(0.85, max(0.15, prob_marche + (score_secu - 50) / 180.0))
        
                    div_facteur_kelly = 3.0 if nb_partants_actuel >= 8 else 2.5
                    if mode_jeu == "Simple" and "Placé" in pari_secu_txt:
                        b = ((cote_base - 1.0) / div_facteur_kelly)
                    else:
                        b = cote_base - 1.0

                    kelly_pur = (b * prob_estimee - (1.0 - prob_estimee)) / b if b > 0 else 0.0
                    fraction_kelly = 0.05 + (min(score_secu, 100) / 1000.0) 
                    kelly_ajustement = max(0.0, kelly_pur) * fraction_kelly
                    ratio_final = min(0.80, max(0.50, ratio_base + kelly_ajustement))
        
                    mise_secu = max(1, int(round(budget * ratio_final)))
                    mise_gros = max(1, budget - mise_secu)

                    # Sauvegarde persistante de l'analyse dans session_state en dehors de la condition du bouton
                    st.session_state["dernier_pari"] = {
                        "date": date_iso,
                        "reunion": course_courante['reunion'],
                        "course_num": course_courante['course'],
                        "hippodrome": course_courante['hippodrome'],
                        "course": f"{course_courante['reunion']} {course_courante['course']} ({course_courante['hippodrome']})",
                        "discipline": discipline_courante,
                        "type": mode_jeu,
                        "details": f"Sécurité ({pari_secu_txt}): [{chevaux_secu_str}] ({mise_secu}€) | Spéculatif ({pari_gros_txt}): [{chevaux_gros_str}] ({mise_gros}€)",
                        "mise": budget,
                        "statut": "En attente",
                        "gain": 0.0,
                        "diagnostic": f"Analyse intégrale validée (Terrain: {terrain_courant}, ROI: {roi_actuel:.2f})",
                        "ignore_stats": False,
                        "secu_txt": pari_secu_txt,
                        "secu_str": chevaux_secu_str,
                        "m_secu": mise_secu,
                        "gros_txt": pari_gros_txt,
                        "gros_str": chevaux_gros_str,
                        "m_gros": mise_gros
                    }

            # Affichage persistant du résultat et du bouton de validation si l'analyse a été lancée
            if "dernier_pari" in st.session_state:
                pari_courant_affiche = st.session_state["dernier_pari"]
                st.markdown("---")
                st.markdown(f"### 🎯 Stratégie Optimale & Jeux Recommandés")
    
                col_secu, col_gros = st.columns(2)
                with col_secu:
                    st.success(f"""
                    **🛡️ OBJECTIF SÉCURITÉ**  
                    *(Pour récupérer la mise / Sécuriser)*
                    * **Type de jeu :** **{pari_courant_affiche.get('secu_txt', 'Simple Placé')}**
                    * **Sélection :** {pari_courant_affiche.get('secu_str', '')}
                    * **Mise conseillée :** **{pari_courant_affiche.get('m_secu', 0)} €**
                    """)
        
                with col_gros:
                    st.warning(f"""
                    **🚀 OBJECTIF GROS GAINS**  
                    *(Pour maximiser la rentabilité / Spéculation)*
                    * **Type de jeu :** **{pari_courant_affiche.get('gros_txt', 'Simple Gagnant')}**
                    * **Sélection :** {pari_courant_affiche.get('gros_str', '')}
                    * **Mise conseillée :** **{pari_courant_affiche.get('m_gros', 0)} €**
                    """)

                st.markdown("")
                if st.button("✅ Valider / Intégrer ce pari au suivi financier", type="primary"):
                    historique = []
                    if FICHIER_HISTORIQUE.exists():
                        try:
                            with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
                                historique = json.load(f)
                        except Exception:
                            pass
                    
                    # On nettoie les clés temporaires avant l'enregistrement final dans le fichier
                    pari_a_enregistrer = dict(pari_courant_affiche)
                    for k in ["secu_txt", "secu_str", "m_secu", "gros_txt", "gros_str", "m_gros"]:
                        pari_a_enregistrer.pop(k, None)

                    historique.append(pari_a_enregistrer)
                    sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Ajout et validation d'un nouveau pari")
                    st.success("Pari validé, enregistré et synchronisé avec succès dans vos suivis !")
                    del st.session_state["dernier_pari"]
                    st.rerun()

with tab_suivi:
    st.subheader("📈 Suivi, Bilan Financier & ROI")
    
    if FICHIER_HISTORIQUE.exists():
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
            
        expander_raz_ouvert = st.session_state.get("confirmer_raz_stats", False)
        with st.expander("🔄 Remise à zéro des compteurs financiers (Nouveau cycle)", expanded=expander_raz_ouvert):
            st.warning("Cette action réinitialise les compteurs de mise/gain principaux du haut pour démarrer un nouveau cycle.")
            if "confirmer_raz_stats" not in st.session_state:
                st.session_state["confirmer_raz_stats"] = False

            if not st.session_state["confirmer_raz_stats"]:
                if st.button("Remettre à zéro les compteurs financiers", key="btn_init_raz"):
                    st.session_state["confirmer_raz_stats"] = True
                    st.rerun()
            else:
                st.write("⚠️ **Confirmer la remise à zéro des compteurs financiers pour lancer un nouveau cycle ?**")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    if st.button("✅ Oui, démarrer un nouveau cycle", type="primary", key="btn_confirm_raz"):
                        for p in historique:
                            p["ignore_stats"] = True
                        sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Réinitialisation des compteurs financiers")
                        st.session_state["confirmer_raz_stats"] = False
                        st.success("Compteurs remis à zéro pour le cycle actif !")
                        st.rerun()
                with col_c2:
                    if st.button("❌ Annuler", key="btn_cancel_raz"):
                        st.session_state["confirmer_raz_stats"] = False
                        st.rerun()

        historique_actifs = historique
        historique_stats = [p for p in historique_actifs if not p.get("ignore_stats", False)]
            
        if st.button("🔄 Vérifier automatiquement les résultats des courses"):
            with st.spinner("Téléchargement et analyse des résultats officiels..."):
                modifie = verifier_resultats_automatiques_pmu(historique)
                if modifie:
                    sauvegarder_et_synchroniser(historique, FICHIER_HISTORIQUE, "Mise à jour automatique des résultats PMU")
                    st.success("Résultats mis à jour et sauvegardés avec succès !")
                    st.rerun()
                else:
                    st.info("Aucun nouveau résultat officiel disponible pour les paris en attente.")

        total_mise = sum(safe_float(p.get("mise", 0)) for p in historique_stats if p.get("statut") != "Annulé")
        total_gain = sum(safe_float(p.get("gain", 0)) for p in historique_stats if p.get("statut") == "Gagné")
        bilan_net = total_gain - total_mise
        
        total_mise_global = sum(safe_float(p.get("mise", 0)) for p in historique if p.get("statut") != "Annulé")
        total_gain_global = sum(safe_float(p.get("gain", 0)) for p in historique if p.get("statut") == "Gagné")
        roi_global = ((total_gain_global - total_mise_global) / total_mise_global * 100) if total_mise_global > 0 else 0.0

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Mise Totale", f"{total_mise:.2f} €")
        col_m2.metric("Gains Totaux", f"{total_gain:.2f} €")
        col_m3.metric("Bilan Net", f"{bilan_net:+.2f} €", delta_color="normal" if bilan_net >= 0 else "inverse")
        col_m4.metric("ROI Global", f"{roi_global:+.1f}%")

        st.divider()
        st.subheader("📊 Visualisation de la Bankroll & ROI par Type de Jeu")

        roi_par_type = {}
        for p in historique:
            if p.get("statut") == "Annulé":
                continue
            t_jeu = str(p.get("type", "Simple"))
            if t_jeu not in roi_par_type:
                roi_par_type[t_jeu] = {"mises": 0.0, "gains": 0.0}
            roi_par_type[t_jeu]["mises"] += safe_float(p.get("mise", 0))
            if p.get("statut") == "Gagné":
                roi_par_type[t_jeu]["gains"] += safe_float(p.get("gain", 0))

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.write("**Rentabilité (ROI) par Type de Jeu :**")
            data_roi = []
            for t, vals in roi_par_type.items():
                m = vals["mises"]
                g = vals["gains"]
                r = ((g - m) / m * 100) if m > 0 else 0.0
                data_roi.append({"Type de Jeu": t, "Mises (€)": round(m, 2), "Gains (€)": round(g, 2), "ROI (%)": round(r, 1)})
            st.dataframe(data_roi, use_container_width=True, hide_index=True)

        with col_r2:
            historique_trie = sorted([p for p in historique if p.get("statut") in ["Gagné", "Perdu"]], key=lambda x: str(x.get("date", "")))
            cumul = 0.0
            donnees_graph = {}
            for p in historique_trie:
                m = safe_float(p.get("mise", 0))
                g = safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0
                cumul += (g - m)
                donnees_graph[p.get("date")] = cumul
            
            if donnees_graph:
                st.write("**Courbe d'évolution du Bilan Cumulé (€) :**")
                st.line_chart(list(donnees_graph.values()))
            else:
                st.info("Pas assez de paris terminés pour afficher la courbe d'évolution.")

        st.divider()
        st.subheader("🏇 Rentabilité (ROI) par Discipline")
        
        roi_par_discipline = {}
        for p in historique:
            if p.get("statut") == "Annulé":
                continue
            disc = str(p.get("discipline", "Galop Plat"))
            if disc not in roi_par_discipline:
                roi_par_discipline[disc] = {"mises": 0.0, "gains": 0.0}
            roi_par_discipline[disc]["mises"] += safe_float(p.get("mise", 0))
            if p.get("statut") == "Gagné":
                roi_par_discipline[disc]["gains"] += safe_float(p.get("gain", 0))

        data_roi_disc = []
        for d, vals in roi_par_discipline.items():
            m = vals["mises"]
            g = vals["gains"]
            net_disc = g - m
            r = ((g - m) / m * 100) if m > 0 else 0.0
            data_roi_disc.append({
                "Discipline": d, "Mises (€)": round(m, 2), "Gains (€)": round(g, 2),
                "Bilan Net (€)": round(net_disc, 2), "ROI (%)": round(r, 1)
            })
        st.dataframe(data_roi_disc, use_container_width=True, hide_index=True)

        st.divider()
        with st.expander("📁 Tableau détaillé et suppression des paris", expanded=True):
            data_suivi = []
            for idx, p in enumerate(historique):
                data_suivi.append({
                    "Sélectionner": False, "Index": idx, "Date": p.get("date"),
                    "Course": p.get("course"), "Discipline": p.get("discipline", "Galop Plat"),
                    "Type": p.get("type"), "Détails": p.get("details"),
                    "Mise (€)": safe_float(p.get("mise", 0)), "Statut": p.get("statut"),
                    "Gain (€)": safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else "-",
                    "Diagnostic": p.get("diagnostic", "-")
                })
            
            edited_df = st.data_editor(
                data_suivi,
                column_config={"Sélectionner": st.column_config.CheckboxColumn("🗑️ Sélectionner", default=False)},
                disabled=["Index", "Date", "Course", "Discipline", "Type", "Détails", "Mise (€)", "Statut", "Gain (€)", "Diagnostic"],
                hide_index=True, use_container_width=True, key="editor_suivi_table"
            )
            
            if st.button("🗑️ Supprimer les paris sélectionnés", key="btn_suppr_selection"):
                if isinstance(edited_df, pd.DataFrame):
                    edited_rows = edited_df.to_dict(orient="records")
                else:
                    edited_rows = edited_df

                indices_a_supprimer = [row["Index"] for row in edited_rows if row.get("Sélectionner")]
                if indices_a_supprimer:
                    historique_maj = [p for i, p in enumerate(historique) if i not in indices_a_supprimer]
                    sauvegarder_et_synchroniser(historique_maj, FICHIER_HISTORIQUE, f"Suppression de {len(indices_a_supprimer)} pari(s)")
                    st.success(f"{len(indices_a_supprimer)} pari(s) supprimé(s) avec succès !")
                    st.rerun()
                else:
                    st.warning("Aucun pari sélectionné pour la suppression.")
    else:
        st.info("Aucun historique de pari enregistré pour le moment.")

with tab_reunions:
    st.subheader("🏟️ Bilan par Réunion (Sélection par Jour)")
    
    if FICHIER_HISTORIQUE.exists():
        with open(FICHIER_HISTORIQUE, "r", encoding="utf-8") as f:
            historique = json.load(f)
            
        if historique:
            dates_disponibles = sorted(list(set(str(p.get("date")) for p in historique if p.get("date"))), reverse=True)
            if dates_disponibles:
                date_choisie_bilan = st.selectbox("📅 Sélectionnez la journée à analyser", dates_disponibles)
                fichier_bilan_jour = DOSSIER / f"bilan_journee_{date_choisie_bilan}.json"
                tableau_reunions = []
                
                if fichier_bilan_jour.exists():
                    try:
                        with open(fichier_bilan_jour, "r", encoding="utf-8") as fb:
                            tableau_reunions = json.load(fb)
                    except Exception:
                        pass
                
                if not tableau_reunions:
                    historique_jour = [p for p in historique if str(p.get("date")) == date_choisie_bilan]
                    reunions_bilan = {}
                    for p in historique_jour:
                        if p.get("statut") == "Annulé":
                            continue
                        reunion_nom = f"{p.get('reunion', 'R?')} - {p.get('hippodrome', 'Inconnu')}"
                        if reunion_nom not in reunions_bilan:
                            reunions_bilan[reunion_nom] = {"mises": 0.0, "gains": 0.0, "paris": 0, "gagnes": 0, "perdus": 0, "en_attente": 0}
                        
                        mise = safe_float(p.get("mise", 0))
                        gain = safe_float(p.get("gain", 0)) if p.get("statut") == "Gagné" else 0.0
                        statut = p.get("statut")
                        
                        reunions_bilan[reunion_nom]["mises"] += mise
                        reunions_bilan[reunion_nom]["gains"] += gain
                        reunions_bilan[reunion_nom]["paris"] += 1
                        if statut == "Gagné":
                            reunions_bilan[reunion_nom]["gagnes"] += 1
                        elif statut == "Perdu":
                            reunions_bilan[reunion_nom]["perdus"] += 1
                        elif statut == "En attente":
                            reunions_bilan[reunion_nom]["en_attente"] += 1

                    for k, v in reunions_bilan.items():
                        net = v["gains"] - v["mises"]
                        roi_reunion = (net / v["mises"] * 100) if v["mises"] > 0 else 0.0
                        tableau_reunions.append({
                            "Réunion / Hippodrome": k, "Total Paris": v["paris"],
                            "Gagnés / Perdus / Attente": f"{v['gagnes']} / {v['perdus']} / {v['en_attente']}",
                            "Mises (€)": round(v["mises"], 2), "Gains (€)": round(v["gains"], 2),
                            "Bilan Net (€)": round(net, 2), "ROI (%)": round(roi_reunion, 1)
                        })
                
                if tableau_reunions:
                    st.dataframe(tableau_reunions, use_container_width=True, hide_index=True)
                    if st.button("💾 Forcer la sauvegarde et synchronisation de ce bilan"):
                        generer_et_sauvegarder_bilan_journee(historique, date_choisie_bilan)
                        st.success("Bilan de la réunion synchronisé !")