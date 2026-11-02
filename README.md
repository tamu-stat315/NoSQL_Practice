# STAT 315 NoSQL practice

These files start MongoDB and Redis with fictional restaurant and leaderboard data. Use them with the course notebook **Working with NoSQL databases**, which explains the queries and includes captured results. You can follow the notebook even if Docker or repository access does not work on your computer during class.

## Get the files

The practice files are in [tamu-stat315/NoSQL_Practice](https://github.com/tamu-stat315/NoSQL_Practice). If GitHub asks you to sign in, use your course GitHub account. If you see a 404 or "Repository not found" message, check the address and your access. Follow the notebook's captured results during class if you cannot download the files.

Open Docker Desktop. Open Git Bash on Windows or Terminal on macOS/Linux. Navigate to the folder where you keep course repositories, then clone once:

```bash
git clone https://github.com/tamu-stat315/NoSQL_Practice.git
cd NoSQL_Practice
```

If you already have this repository, open a terminal in that existing folder instead. Do not clone it inside itself. Use `git status` before `git pull --ff-only`; stop if you have local edits you need to keep. These Git commands were introduced in Module 1.

The Compose project is `stat315-nosql-practice`, separate from the course SQL environment. Run all Docker commands below from the folder containing `compose.yaml`.

## If MongoDB would not start on your Mac

The November 2 update addresses a MongoDB startup problem with the Linux kernel inside some Docker Desktop versions. The report may mention `SERVER-121912` or incompatible Linux kernel versions. This can happen on Apple Silicon Macs even though macOS itself does not use a Linux kernel.

Open Terminal in your existing `NoSQL_Practice` folder and run:

```bash
git status
```

If Git lists local changes, stop and keep those changes before updating. If your working tree is clean, run:

```bash
git pull --ff-only
docker compose up --detach --wait --wait-timeout 180
docker compose ps --all
```

Both services should show `healthy`. Compose recreates MongoDB with the updated setting and reuses your saved database volume. This does not reset your restaurant edits or Redis scores. `docker compose restart` alone will not apply the change.

Check MongoDB from your normal terminal:

```bash
docker compose exec -T mongo mongosh --quiet stat315_nosql --eval 'db.restaurants.countDocuments()'
docker compose exec -T mongo mongosh --quiet --eval 'db.serverStatus().tcmalloc.usingPerCPUCaches'
```

The first command should print `8` if you have not added or removed documents. The second should print `false`, confirming that the compatibility setting is active. It does not mean MongoDB failed.

If MongoDB still exits or stays unhealthy, run these commands and keep the output:

```bash
docker compose version
docker info --format 'Docker {{.ServerVersion}} | {{.OSType}}/{{.Architecture}} | kernel {{.KernelVersion}}'
docker compose ps --all
docker compose logs --no-color --tail=100 mongo
docker inspect --format 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}}' "$(docker compose ps --all --quiet mongo)"
```

Send me that output and your Mac's chip model. If Docker cannot connect to its engine, open Docker Desktop and wait for it to finish starting before trying again. If `oom=true`, Docker stopped MongoDB because it ran out of memory; include that result rather than deleting the database.

If MongoDB responds to queries but shows fewer than eight documents before you have added or removed any, its first startup may have stopped before all the sample data loaded. The health check only looks for `R01`, so a `healthy` status does not guarantee that all eight documents are present. Use the restaurant restore command below only if you want to restore the eight supplied documents. That command replaces edits to those eight documents, so do not run it as a general startup fix.

The update keeps MongoDB 8.0.34 and adds `GLIBC_TUNABLES: "glibc.pthread.rseq=1"` under the MongoDB service's `environment` settings. This selects a memory allocator mode that avoids the affected per-CPU cache path. It is the [workaround recommended by the official image maintainers](https://github.com/docker-library/mongo/discussions/748). [MongoDB documents the kernel issue](https://www.mongodb.com/docs/v8.0/release-notes/8.0/) and identifies Linux 7.0.14 or later as the kernel fix.

Keep the supplied image and native architecture selection. Do not switch to MongoDB 8.0.4, 7.0, or 6.0, add `platform: linux/amd64`, or delete volumes to troubleshoot this error. Version 8.0.4 is older than 8.0.34, and changing major versions can make existing database files incompatible. If the problem continues during class, follow the notebook's captured results while we review the error.

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

**This restores the eight supplied restaurant documents and discards changes you made to those documents.** It leaves any additional documents you created in place and does not affect the SQL environment. Reloading `redis_seed.txt` restores only the supplied Redis teaching keys. Do not use global cleanup commands, `FLUSHALL`, or `docker compose down --volumes` to solve a setup problem.

## Files

- `compose.yaml`: the two services, health checks, isolated network, and named volumes. Exact image digests keep the tested versions identifiable.
- `mongo_seed/01_restaurants.js`: eight fictional restaurant records, loaded on the first MongoDB startup.
- `redis_seed.txt`: the announcement, four player-name hashes, and leaderboard. Loading it restores these teaching keys to their starting values.

The services have no published host ports and listen on loopback inside their containers. They have no authentication and are only for local synthetic-data practice, not shared or production use. Do not add port mappings. No additional database client or Python installation is required on the host.

The current setup has been tested on an Intel Mac. Windows Git Bash checks cover command input, file paths, line endings, and Compose configuration; a complete Windows Docker Desktop run and an Apple Silicon Mac run are still unverified. Both AMD64 and ARM64 images are available. If setup fails, use the notebook's captured results and keep the error message for later help. This single-machine practice environment does not demonstrate CAP behavior during a network partition.
