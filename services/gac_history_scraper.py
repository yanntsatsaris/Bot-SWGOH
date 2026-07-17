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
        self.total_tasks = {}
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

    async def queue_scrape(self, ally_code: str, interaction=None, callback=None, format_filter=None):
        """Ajoute un joueur à la file d'attente pour être scrapé."""
        if ally_code.startswith("batch_") and ally_code.endswith(".txt"):
            clean_code = ally_code.replace("batch_", "").replace(".txt", "")
        elif ally_code.startswith("http"):
            round_info = self._extract_round_info_from_url(ally_code)
            clean_code = round_info["ally_code"] if round_info and round_info.get("ally_code") else "unknown"
        else:
            clean_code = ally_code.replace("-", "").strip()

        if clean_code == "unknown":
            return

        if clean_code not in self.interactions:
            self.interactions[clean_code] = {"interactions": [], "callbacks": []}

        if interaction:
            self.interactions[clean_code]["interactions"].append(interaction)
        if callback:
            self.interactions[clean_code]["callbacks"].append((interaction, callback))

        is_batch = str(ally_code).startswith("batch_")
        
        # Ne pas re-queuter si c'est déjà en attente et ce n'est pas un batch
        if not is_batch and self.pending_tasks.get(clean_code, 0) > 0:
            logger.info(f"⏭️ {clean_code} est déjà en cours de scraping. Ajout aux abonnés.")
            return

        self.pending_tasks[clean_code] = self.pending_tasks.get(clean_code, 0) + 1
        self.total_tasks[clean_code] = self.total_tasks.get(clean_code, 0) + 1

        await self.queue.put((ally_code, interaction, format_filter))
        logger.info(f"Ajout de {ally_code} à la file d'attente de scraping. (Taille: {self.queue.qsize()})")

    async def _worker_loop(self):
        """Boucle principale qui dépile et traite les requêtes."""
        while self.is_running:
            try:
                # Attend qu'un profil soit ajouté à la file
                ally_code, interaction, format_filter = await self.queue.get()
                
                logger.info(f"⚙️ Démarrage du scraping pour {ally_code}...")
                
                if interaction:
                    try:
                        if not str(ally_code).startswith("batch_"):
                            await interaction.edit_original_response(content=f"⏳ **[■■■□□□□□□□] 30%** : Démarrage de l'extraction pour l'ally code **{ally_code}**...")
                    except Exception as e:
                        logger.error(f"Erreur update Discord (début scraping): {e}")             
                # Exécute la fonction bloquante SeleniumBase dans un processus séparé isolé !
                # Ça évite tous les deadlocks liés à asyncio / Xvfb
                if ally_code.startswith("batch_") and ally_code.endswith(".txt"):
                    target_url = ally_code
                    clean_code = ally_code.replace("batch_", "").replace(".txt", "")
                elif ally_code.startswith("http"):
                    target_url = ally_code
                    clean_code = "custom_url"
                else:
                    target_url = f"https://swgoh.gg/p/{ally_code}/gac-history/"
                    clean_code = ally_code
                
                # Définir le code utilisateur cible pour le suivi de la tâche de fin
                if target_url.endswith('.txt'):
                    r_info = None
                    c_code = clean_code
                else:
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
                                        if interaction:
                                            try:
                                                import re
                                                progress_match = re.search(r"\((\d+)/(\d+)\) Chargement", msg)
                                                if progress_match:
                                                    current = int(progress_match.group(1))
                                                    total = int(progress_match.group(2))
                                                    if total > 1 and (current == 1 or current == total or current % 5 == 0):
                                                        pct = int((current / total) * 60) + 10
                                                        bars = int((pct / 100) * 10)
                                                        bar_str = "■" * bars + "□" * (10 - bars)
                                                        
                                                        # Update all interactions
                                                        saved_int = self.interactions.get(clean_code, {})
                                                        for inter in saved_int.get("interactions", []):
                                                            try:
                                                                asyncio.create_task(inter.edit_original_response(content=f"⏳ **[{bar_str}] {pct}%** : Extraction continue en cours ({current}/{total})..."))
                                                            except: pass
                                                elif "Cloudflare détecté" in msg or "Pas de Cloudflare" in msg:
                                                    pass # On ignore pour ne pas spammer pendant le batch
                                                elif "Contenu GAC détecté" in msg:
                                                    pass # Idem
                                            except Exception as e:
                                                logger.error(f"Erreur update Discord: {e}")

                        # On lance la lecture en parallèle
                        await asyncio.wait_for(
                            asyncio.gather(
                                read_stream(process.stdout),
                                read_stream(process.stderr, is_error=True),
                                process.wait()
                            ),
                            timeout=600.0
                        )
                        
                        if process.returncode == 0:
                            logger.info(f"✅ Subprocess a réussi (Code 0)")
                            
                            if interaction:
                                try:
                                    await interaction.edit_original_response(content=f"⏳ **[■■■■■■■□□□] 70%** : Données brutes récupérées, préparation du traitement...")
                                except:
                                    pass
                            
                            # On lit le fichier généré par le worker
                            safe_name = clean_code.replace("/", "_").replace(":", "")
                            file_path = f"gac_history_{safe_name}.html"
                            
                            import os
                            if os.path.exists(file_path):
                                with open(file_path, "r", encoding="utf-8") as f:
                                    html_content = f.read()
                                    
                                logger.info(f"Analyse du HTML en cours ({len(html_content)} caractères)...")
                                loop = asyncio.get_running_loop()
                                parsed_results = await loop.run_in_executor(None, self._parse_html, html_content, clean_code, target_url, format_filter)
                                
                                total_matchs = 0
                                for parsed_data in parsed_results:
                                    # Si on a atterri sur la page d'accueil GAC, on filtre et on batch
                                    if parsed_data.get("hub_links"):
                                        logger.info("🔗 Page d'accueil détectée. Filtrage des rounds existants...")
                                        from database.db import get_db
                                        links_to_scrape = []
                                        async with get_db() as db:
                                            for link in parsed_data["hub_links"]:
                                                r_info = self._extract_round_info_from_url(link)
                                                if r_info:
                                                    cursor = await db.execute(
                                                        "SELECT id FROM gac_rounds WHERE player_code=? AND season_id=? AND round_number=?",
                                                        (r_info["ally_code"], r_info["season_id"], r_info["round"])
                                                    )
                                                    if not await cursor.fetchone():
                                                        links_to_scrape.append(link)
                                        
                                        if links_to_scrape:
                                            logger.info(f"🔗 {len(links_to_scrape)} nouveaux rounds à scraper. Création du batch...")
                                            batch_file = f"batch_{clean_code}.txt"
                                            with open(batch_file, "w") as bf:
                                                bf.write("\n".join(links_to_scrape))
                                                
                                            # On met le fichier texte dans la file
                                            await self.queue_scrape(batch_file, interaction=interaction, format_filter=format_filter)
                                            
                                            if interaction:
                                                try:
                                                    await interaction.edit_original_response(content=f"⏳ **[■■■■■■□□□□] 60%** : {len(links_to_scrape)} nouveaux rounds trouvés ! Lancement de l'extraction continue...")
                                                except:
                                                    pass
                                        else:
                                            logger.info("✅ Aucun nouveau round à scraper (tous déjà en BDD).")
                                            if interaction:
                                                try:
                                                    await interaction.edit_original_response(content=f"⏳ **[■■■■■■■■■□] 90%** : Historique déjà à jour !")
                                                except:
                                                    pass
                                        continue
                                    
                                    # Sinon c'est un match normal, on sauvegarde en base de données
                                    from database.db import save_gac_history_to_db
                                    url_for_db = parsed_data.get("url", target_url)
                                    await save_gac_history_to_db(parsed_data, url_for_db)
                                    total_matchs += len(parsed_data.get("matches", []))
                                
                                if interaction and total_matchs > 0:
                                    try:
                                        await interaction.edit_original_response(content=f"⏳ **[■■■■■■■■■□] 90%** : {total_matchs} combats extraits avec succès ! Préparation de l'analyse...")
                                    except:
                                        pass
                            else:
                                logger.error(f"Fichier {file_path} introuvable après le scraping.")
                        else:
                            logger.error(f"❌ Échec du Subprocess (Code {process.returncode})")
                            if interaction:
                                try:
                                    await interaction.edit_original_response(content=f"❌ **Erreur** : L'extraction a échoué.")
                                except:
                                    pass
                    except asyncio.TimeoutError:
                        process.kill()
                        logger.error(f"⏰ Timeout: Le processus de scraping a été tué car il a mis plus de 600 secondes.")
                        if interaction:
                            try:
                                await interaction.edit_original_response(content=f"❌ **Timeout** : Le traitement a été interrompu (trop long ou Cloudflare bloquant).")
                            except:
                                pass
                finally:
                    self.queue.task_done()
                    if c_code in self.pending_tasks:
                        self.pending_tasks[c_code] -= 1
                        
                        # L'ancienne barre de progression "1/2 complétés" a été retirée
                        # car le Subprocess gère son propre % avec le batch (1/63 -> 63/63).
                        
                        # --- Nettoyage des fichiers temporaires ---
                        import os
                        safe_name = c_code.replace("/", "_").replace(":", "")
                        files_to_remove = [
                            f"gac_history_{safe_name}.html",
                            "selenium_result.png",
                            "cloudflare_block.png",
                            "cloudflare_block.html",
                            "cloudflare_after_click.png"
                        ]
                        if str(ally_code).startswith("batch_"):
                            files_to_remove.append(f"batch_{safe_name}.txt")
                            
                        for f in files_to_remove:
                            if os.path.exists(f):
                                try:
                                    os.remove(f)
                                except Exception as e:
                                    logger.error(f"Erreur lors de la suppression du fichier temp {f}: {e}")
                        # ----------------------------------------
                        
                        if self.pending_tasks[c_code] <= 0:
                            del self.pending_tasks[c_code]
                            if c_code in self.total_tasks:
                                del self.total_tasks[c_code]
                            saved_int = self.interactions.pop(c_code, None)
                            if saved_int and saved_int.get("callbacks"):
                                for inter, cb in saved_int["callbacks"]:
                                    asyncio.create_task(cb(c_code, inter))
                
                # Petite pause entre chaque profil pour ne pas affoler Cloudflare
                await asyncio.sleep(5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur critique dans le worker GAC Scraper : {e}")
                await asyncio.sleep(5)

    def _parse_html(self, html: str, ally_code: str, default_target_url: str = "", format_filter: str = None) -> list[dict]:
        """
        Analyse l'HTML brut de swgoh.gg pour extraire les rounds et les équipes complètes.
        Supporte les fichiers contenant plusieurs pages séparées par <hr>.
        """
        import re
        from bs4 import BeautifulSoup
        
        results = []
        chunks = html.split('<hr>')
        
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
                
            target_url = default_target_url
            # Récupérer l'URL injectée par le worker si elle existe
            url_match = re.search(r"<!-- URL:\s*(https?://[^\s]+)\s*-->", chunk)
            if url_match:
                target_url = url_match.group(1)
                
            try:
                soup = BeautifulSoup(chunk, 'html.parser')
                matches = []
                parsed_league = None
                
                def parse_section(section_div, is_attack: bool):
                    nonlocal parsed_league
                    if not section_div: return
                    
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
                        
                        if not parsed_league:
                            parent_summary = block.find_parent('div', class_='gac-counters-battle-summary')
                            if parent_summary:
                                league_img = parent_summary.find('img', class_='gac-counters-battle-summary__league-icon-division')
                                if league_img and 'src' in league_img.attrs:
                                    src = league_img['src'].lower()
                                    if 'bronzium' in src: parsed_league = 'BRONZIUM'
                                    elif 'chromium' in src: parsed_league = 'CHROMIUM'
                                    elif 'aurodium' in src: parsed_league = 'AURODIUM'
                                    elif 'kyber' in src: parsed_league = 'KYBER'
                                    elif 'carbonite' in src: parsed_league = 'CARBONITE'
                                    
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
                                elif label == "zone":
                                    svg = value_el.find('svg')
                                    if svg:
                                        paths = svg.find_all('path')
                                        for i, path in enumerate(paths):
                                            classes = path.get('class', [])
                                            if isinstance(classes, str):
                                                classes = classes.split()
                                            if 'gac-zone-layout--is-active' in classes:
                                                zone_map = {0: "top", 1: "bottom", 2: "fleet", 3: "back"}
                                                match_data["zone"] = zone_map.get(i, "unknown")
                                                break
                                                
                        parent = block.parent
                        if parent:
                            squad_containers = parent.find_all('div', class_='gac-battle-portrait-layout')
                            if squad_containers and len(squad_containers) >= 2:
                                a_units = squad_containers[0].find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
                                match_data["attacker_team"] = [u['data-unit-def-tooltip-app'] for u in a_units]
                                if match_data["attacker_team"]:
                                    match_data["attacker_lead"] = match_data["attacker_team"][0]
                                    
                                d_units = squad_containers[1].find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
                                match_data["defender_team"] = [u['data-unit-def-tooltip-app'] for u in d_units]
                                if match_data["defender_team"]:
                                    match_data["defender_lead"] = match_data["defender_team"][0]
                                    
                        matches.append(match_data)

                parse_section(soup.find('div', id='battles-attack'), is_attack=True)
                parse_section(soup.find('div', id='battles-defense'), is_attack=False)
                    
                is_hub_page = target_url.endswith('gac-history/') if target_url else not matches
                if is_hub_page:
                    hub_links = []
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if "/gac-history/" in href and (href.endswith('/1/') or href.endswith('/2/') or href.endswith('/3/')):
                            full_url = f"https://swgoh.gg{href}" if href.startswith('/') else href
                            if full_url not in hub_links: hub_links.append(full_url)
                    if hub_links:
                        hub_links_sorted = sorted(hub_links, key=lambda u: u.split("/gac-history/")[-1].split("/")[0], reverse=True)
                        unique_seasons = []
                        filtered_links = []
                        for link in hub_links_sorted:
                            s_id = link.split("/gac-history/")[-1].split("/")[0]
                            if s_id not in unique_seasons:
                                if len(unique_seasons) >= 2:
                                    break
                                unique_seasons.append(s_id)
                            filtered_links.append(link)
                            
                        results.append({"matches": [], "hub_links": filtered_links, "url": target_url})
                        continue
                    
                land_matches = [m for m in matches if not (m.get("defender_lead") and ("CAPITAL" in str(m["defender_lead"]) or m["defender_lead"] in ["CAPITALSTARDESTROYER", "CAPITALCHIMAERA", "CAPITALEXECUTOR", "CAPITALPROFUNDITY", "CAPITALNEGOTIATOR", "CAPITALMALEVOLENCE", "CAPITALRADDUS", "CAPITALFINALIZER", "CAPITALLEVIATHAN"]))]
                max_size = max((len(m["defender_team"]) for m in land_matches if m["defender_team"]), default=5)
                detected_format = "3v3" if max_size <= 3 else "5v5"
                
                if format_filter and detected_format != format_filter:
                    logger.info(f"🚫 Match ignoré car le format détecté ({detected_format}) ne correspond pas au filtre ({format_filter}) pour {target_url}")
                    continue
                    
                logger.info(f"✅ Extrait : {len(matches)} matchs pour {target_url} (Ligue: {parsed_league})")
                results.append({"matches": matches, "format": detected_format, "league": parsed_league, "url": target_url})
                
            except Exception as e:
                logger.error(f"Erreur lors du parsing HTML pour le chunk {target_url} : {e}")
                
        return results
