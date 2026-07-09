import asyncio
import logging
import concurrent.futures
from bs4 import BeautifulSoup
from seleniumbase import SB

logger = logging.getLogger("gac_scraper")

class GACHistoryScraper:
    def __init__(self, db_manager):
        self.db = db_manager
        self.queue = asyncio.Queue()
        self.is_running = False
        self._worker_task = None
        # On utilise un ThreadPool de 1 pour être sûr qu'un seul Chrome tourne à la fois
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.pending_tasks = {}
        self.interactions = {}

    def _extract_round_info_from_url(self, url: str) -> dict | None:
        """
        Extrait ally_code, season_id et round_number depuis une URL swgoh.gg.
        Ex: https://swgoh.gg/p/266539582/gac-history/O1782248400000/1/
        """
        if "gac-history/" not in url:
            return None
        parts = [p for p in url.split("/") if p]
        try:
            p_idx = parts.index("p")
            hist_idx = parts.index("gac-history")
            return {
                "ally_code": parts[p_idx + 1],
                "season_id": parts[hist_idx + 1],
                "round": int(parts[hist_idx + 2]) if len(parts) > hist_idx + 2 else None,
            }
        except (ValueError, IndexError):
            return None

    async def start(self):
        """Démarre le worker en arrière-plan."""
        if not self.is_running:
            self.is_running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("🟢 Scraper GAC History démarré.")

    async def stop(self):
        """Arrête proprement le scraper."""
        self.is_running = False
        if self._worker_task:
            self._worker_task.cancel()
        self.executor.shutdown(wait=True)
        logger.info("🔴 Scraper GAC History arrêté.")

    async def queue_scrape(self, ally_code: str, interaction=None, callback=None):
        """Ajoute un joueur à la file d'attente pour être scrapé."""
        if interaction:
            clean_code = ally_code.replace("-", "").strip() if not ally_code.startswith("http") else self._extract_round_info_from_url(ally_code).get("ally_code", "unknown")
            if clean_code != "unknown":
                self.interactions[clean_code] = {"interaction": interaction, "callback": callback}
                self.pending_tasks[clean_code] = self.pending_tasks.get(clean_code, 0) + 1
        else:
            round_info = self._extract_round_info_from_url(ally_code)
            if round_info and round_info.get("ally_code"):
                clean_code = round_info["ally_code"]
                self.pending_tasks[clean_code] = self.pending_tasks.get(clean_code, 0) + 1

        await self.queue.put((ally_code, interaction))
        logger.info(f"Ajout de {ally_code} à la file d'attente de scraping. (Taille: {self.queue.qsize()})")

    async def _worker_loop(self):
        """Boucle principale qui dépile et traite les requêtes."""
        while self.is_running:
            try:
                # Attend qu'un profil soit ajouté à la file
                ally_code, interaction = await self.queue.get()
                
                logger.info(f"⚙️ Démarrage du scraping pour {ally_code}...")
                
                if interaction:
                    try:
                        await interaction.edit_original_response(content=f"⏳ **[■■■□□□□□□□] 30%** : Démarrage de l'extraction pour l'ally code **{ally_code}**...")
                    except:
                        pass
                
                # Exécute la fonction bloquante SeleniumBase dans un processus séparé isolé !
                # Ça évite tous les deadlocks liés à asyncio / Xvfb
                if ally_code.startswith("http"):
                    target_url = ally_code
                    clean_code = "custom_url"
                else:
                    target_url = f"https://swgoh.gg/p/{ally_code}/gac-history/"
                    clean_code = ally_code
                
                # Définir le code utilisateur cible pour le suivi de la tâche de fin
                r_info = self._extract_round_info_from_url(target_url)
                c_code = r_info["ally_code"] if r_info else clean_code

                try:
                    # Vérification anti-doublon AVANT scraping
                    if r_info and r_info.get("round"):
                        from database.db import get_db
                        async with get_db() as db:
                            cursor = await db.execute(
                                "SELECT id FROM gac_rounds WHERE player_code=? AND season_id=? AND round_number=?",
                                (r_info["ally_code"], r_info["season_id"], r_info["round"])
                            )
                            if await cursor.fetchone():
                                logger.info(f"⏭️ Round déjà en BDD, skip du scraping pour {target_url}")
                                continue
                    
                    import sys
                    process = await asyncio.create_subprocess_exec(
                        sys.executable, "scripts/sb_worker.py", target_url, clean_code,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    try:
                        # Fonction pour lire les logs en temps réel
                        async def read_stream(stream, is_error=False):
                            async for line in stream:
                                msg = line.decode().strip()
                                if msg:
                                    if is_error:
                                        logger.error(f"[WORKER] {msg}")
                                    else:
                                        logger.info(f"{msg}")

                        # On lance la lecture en parallèle
                        await asyncio.wait_for(
                            asyncio.gather(
                                read_stream(process.stdout),
                                read_stream(process.stderr, is_error=True),
                                process.wait()
                            ),
                            timeout=150.0
                        )
                        
                        if process.returncode == 0:
                            logger.info(f"✅ Subprocess a réussi (Code 0)")
                            
                            # On lit le fichier généré par le worker
                            safe_name = clean_code.replace("/", "_").replace(":", "")
                            file_path = f"gac_history_{safe_name}.html"
                            
                            import os
                            if os.path.exists(file_path):
                                with open(file_path, "r", encoding="utf-8") as f:
                                    html_content = f.read()
                                    
                                logger.info(f"Analyse du HTML en cours ({len(html_content)} caractères)...")
                                parsed_data = self._parse_html(html_content, clean_code, target_url)
                                
                                # Si on a atterri sur la page d'accueil GAC, on remet les matchs trouvés dans la file d'attente
                                if parsed_data.get("hub_links"):
                                    logger.info("🔗 Page d'accueil détectée. Ajout automatique des sous-liens GAC dans la file d'attente...")
                                    for link in parsed_data["hub_links"]:
                                        # On met interaction=None pour ne pas spammer le channel Discord à chaque sous-lien
                                        await self.queue_scrape(link, interaction=None)
                                    
                                    if interaction:
                                        try:
                                            await interaction.edit_original_response(content=f"⏳ **[■■■■■■□□□□] 60%** : {len(parsed_data['hub_links'])} matchs trouvés ! Traitement en arrière-plan...")
                                        except:
                                            pass
                                    continue
                                
                                # Sinon c'est un match normal, on sauvegarde en base de données
                                from database.db import save_gac_history_to_db
                                await save_gac_history_to_db(parsed_data, target_url)
                                
                                if interaction:
                                    try:
                                        nb_matchs = len(parsed_data.get("matches", []))
                                        await interaction.edit_original_response(content=f"⏳ **[■■■■■■■■■□] 90%** : {nb_matchs} combats extraits avec succès ! Préparation de l'analyse...")
                                    except:
                                        pass
                            else:
                                logger.error(f"Fichier {file_path} introuvable après le scraping.")
                        else:
                            logger.error(f"❌ Échec du Subprocess (Code {process.returncode})")
                            if interaction:
                                try:
                                    await interaction.edit_original_response(content=f"❌ **Erreur** : Le scraping a échoué.")
                                except:
                                    pass
                    except asyncio.TimeoutError:
                        process.kill()
                        logger.error(f"⏰ Timeout: Le processus de scraping a été tué car il a mis plus de 60 secondes.")
                        if interaction:
                            try:
                                await interaction.edit_original_response(content=f"❌ **Timeout** : Cloudflare a fait planter le navigateur.")
                            except:
                                pass
                finally:
                    self.queue.task_done()
                    if c_code in self.pending_tasks:
                        self.pending_tasks[c_code] -= 1
                        if self.pending_tasks[c_code] <= 0:
                            del self.pending_tasks[c_code]
                            saved_int = self.interactions.pop(c_code, None)
                            if saved_int and saved_int.get("callback"):
                                asyncio.create_task(saved_int["callback"](c_code, saved_int["interaction"]))
                
                # Petite pause entre chaque profil pour ne pas affoler Cloudflare
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur critique dans le worker GAC Scraper : {e}")
                await asyncio.sleep(5)

    def _parse_html(self, html: str, ally_code: str, target_url: str = "") -> dict:
        """
        Analyse l'HTML brut de swgoh.gg pour extraire les rounds et les équipes complètes.
        Sépare les attaques et les défenses.
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            matches = []
            
            def parse_section(section_div, is_attack: bool):
                stats_blocks = section_div.find_all('div', class_=lambda c: c and 'gac-counters-battle-summary__stats' in c)
                for block in stats_blocks:
                    match_data = {
                        "banners": 0,
                        "attempt": 1,
                        "outcome": "Unknown",
                        "attacker_lead": "UNKNOWN",
                        "defender_lead": "UNKNOWN",
                        "attacker_team": [],
                        "defender_team": [],
                        "is_attack": is_attack
                    }
                    
                    # Extraction des statistiques
                    stats = block.find_all('div', class_=lambda c: c and 'gac-counters-battle-summary__stat' in c)
                    for stat in stats:
                        label_el = stat.find('div', class_=lambda c: c and 'stat-label' in c)
                        value_el = stat.find('div', class_=lambda c: c and 'stat-value' in c)
                        if label_el and value_el:
                            label = label_el.get_text(strip=True).lower()
                            value = value_el.get_text(strip=True)
                            if label == "banners":
                                match_data["banners"] = int(value) if value.isdigit() else 0
                            elif label == "attempt":
                                match_data["attempt"] = int(value) if value.isdigit() else 1
                            elif label == "outcome":
                                match_data["outcome"] = value
                                
                    parent = block.parent
                    if parent:
                        # Extraction des équipes complètes
                        squad_containers = parent.find_all('div', class_=lambda c: c and 'gac-battle-portrait-layout--character' in c)
                        if squad_containers and len(squad_containers) >= 2:
                            # Attaquant
                            a_units = squad_containers[0].find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
                            match_data["attacker_team"] = [u['data-unit-def-tooltip-app'] for u in a_units]
                            if match_data["attacker_team"]:
                                match_data["attacker_lead"] = match_data["attacker_team"][0]
                                
                            # Défenseur
                            d_units = squad_containers[1].find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
                            match_data["defender_team"] = [u['data-unit-def-tooltip-app'] for u in d_units]
                            if match_data["defender_team"]:
                                match_data["defender_lead"] = match_data["defender_team"][0]
                                
                    matches.append(match_data)

            # Analyse des deux sections
            attack_div = soup.find('div', id='battles-attack')
            if attack_div:
                parse_section(attack_div, is_attack=True)
                
            defense_div = soup.find('div', id='battles-defense')
            if defense_div:
                parse_section(defense_div, is_attack=False)
                
            # On vérifie si c'est vraiment la page HUB (l'URL se termine par gac-history/)
            is_hub_page = target_url.endswith('gac-history/') if target_url else not matches
            
            if is_hub_page:
                # On est sur la page HUB générale (la liste de toutes les saisons)
                # On cherche les liens vers les matchs individuels
                hub_links = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if "/gac-history/" in href and (href.endswith('/1/') or href.endswith('/2/') or href.endswith('/3/')):
                        full_url = f"https://swgoh.gg{href}" if href.startswith('/') else href
                        if full_url not in hub_links:
                            hub_links.append(full_url)
                            
                            
                if hub_links:
                    # L'utilisateur souhaite extraire la totalité de l'historique disponible.
                    # On trie pour prendre les plus récentes (les IDs sont des timestamps)
                    hub_links_sorted = sorted(hub_links, key=lambda u: u.split("/gac-history/")[-1].split("/")[0], reverse=True)
                    # On ne limite plus, on prend toutes les saisons trouvées
                    logger.info(f"🔗 Page Hub détectée, {len(hub_links_sorted)} sous-liens de matchs trouvés ! (Toutes les saisons)")
                    return {"matches": [], "hub_links": hub_links_sorted}
                
            # Détection du format 5v5 vs 3v3
            max_size = max((len(m["attacker_team"]) for m in matches if m["attacker_team"]), default=5)
            detected_format = "3v3" if max_size <= 3 else "5v5"
                
            logger.info(f"✅ Scraping terminé pour {ally_code} : {len(matches)} matchs extraits !")
            return {"matches": matches, "format": detected_format}
            
        except Exception as e:
            logger.error(f"Erreur lors du parsing HTML pour {ally_code} : {e}")
            return {"matches": []}
