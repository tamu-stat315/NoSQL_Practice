# STAT 315 NoSQL practice

These files start MongoDB and Redis with fictional restaurant and leaderboard data. Use them with the course notebook **Working with NoSQL databases**, which explains the queries and includes captured results. You can follow the notebook even if Docker or repository access does not work on your computer during class.

## Get the files

The course repository is [tamu-stat315/NoSQL_Practice](https://github.com/tamu-stat315/NoSQL_Practice). It is currently private; sign in with the GitHub account that has course access. A 404 or "Repository not found" message can mean that access has not been granted. Follow the notebook's results during class if access fails, and ask the instructor afterward.

Open Docker Desktop. Open Git Bash on Windows or Terminal on macOS/Linux. Navigate to the folder where you keep course repositories, then clone once:

```bash
git clone https://github.com/tamu-stat315/NoSQL_Practice.git
cd NoSQL_Practice
```

If you already have this repository, open a terminal in that existing folder instead. Do not clone it inside itself. Use `git status` before `git pull --ff-only`; stop if you have local edits you need to keep. These Git commands were introduced in Module 1.

The Compose project is `stat315-nosql-practice`, separate from the course SQL environment. Run all Docker commands below from the folder containing `compose.yaml`.

## Quick reference after reading the notebook

Start:

```bash
docker compose up --detach --wait
docker compose ps
```

`up` starts the services and downloads their images if needed. `--detach` returns your terminal prompt while the services run. `--wait` waits for their health checks; `ps` lists their status. The first download may take several minutes. If setup is not ready when the activity starts, work from the notebook's screenshots and results.

Open MongoDB:

```bash
docker compose exec mongo mongosh --quiet stat315_nosql
```

`exec` runs a command in a running service; `mongo` is the service name and `mongosh` is its client. `--quiet` reduces startup messages; `stat315_nosql` selects the practice database. The eight restaurant documents load automatically when the database volume is first created.

Enter `exit` in MongoDB to return to your normal terminal. Load the initial Redis data, then open Redis with plain output:

```bash
docker compose exec -T redis redis-cli < redis_seed.txt
docker compose exec redis redis-cli --raw
```

`redis` is the service name and `redis-cli` is its client. `<` supplies the seed file as input; `-T` disables interactive-terminal handling for that file input. `--raw` prints plain results. Loading the seed restores the supplied Redis teaching keys; do not reload it during the score-update exercise unless you intend to restart that exercise.

Enter `QUIT` in Redis to return to your normal terminal. Stop the practice services without deleting their volumes:

```bash
docker compose down
```

Starting again keeps saved changes. To restore the eight fictional restaurant records, first exit `mongosh`, then run this in your normal terminal while the services are running:

```bash
docker compose exec -T mongo mongosh --quiet < mongo_seed/01_restaurants.js
```

**This replaces the practice restaurant collection and discards changes you made to it.** It does not affect the SQL environment. Reloading `redis_seed.txt` restores only the supplied Redis teaching keys. Do not use global cleanup commands, `FLUSHALL`, or `docker compose down --volumes` to solve a setup problem.

## Files

- `compose.yaml`: the two services, health checks, isolated network, and named volumes. Exact image digests keep the tested versions identifiable.
- `mongo_seed/01_restaurants.js`: eight fictional restaurant records, loaded on the first MongoDB startup.
- `redis_seed.txt`: the announcement, four player-name hashes, and leaderboard. Loading it restores these teaching keys to their starting values.

The services have no published host ports and listen on loopback inside their containers. They have no authentication and are only for local synthetic-data practice, not shared or production use. Do not add port mappings. No additional database client or Python installation is required on the host.

Native Intel Mac execution is tested. Image support and any emulation checks do not establish that Windows or a native Apple Silicon computer has been tested. If setup fails, use the notebook's captured results and keep the error message for later help. This single-machine practice environment does not demonstrate CAP behavior during a network partition.
