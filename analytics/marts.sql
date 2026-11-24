-- Analytics marts. Executed by transform/run.py with DuckDB; each CREATE TABLE is exported
-- to data/processed/marts/<name>.parquet. Inputs: views `jobs` and `job_skills`.

-- 1. Share of HN posts mentioning each skill, by month ------------------------------------
CREATE OR REPLACE TABLE skill_trends_monthly AS
WITH posts AS (
    SELECT job_id, date_trunc('month', posted_at)::DATE AS month FROM jobs WHERE source = 'hn'
), totals AS (
    SELECT month, count(*) AS total_posts FROM posts GROUP BY 1
)
SELECT p.month, s.skill, s.category,
       count(*)                                   AS posts,
       t.total_posts,
       round(count(*) * 100.0 / t.total_posts, 2) AS share_pct
FROM posts p
JOIN job_skills s USING (job_id)
JOIN totals t USING (month)
GROUP BY p.month, s.skill, s.category, t.total_posts
ORDER BY month, posts DESC;

-- 2. Skill co-occurrence (network chart) --------------------------------------------------
CREATE OR REPLACE TABLE skill_pairs AS
WITH n AS (SELECT count(DISTINCT job_id) AS n_jobs FROM job_skills),
     freq AS (SELECT skill, count(*) AS n FROM job_skills GROUP BY 1)
SELECT a.skill AS skill_a, b.skill AS skill_b,
       count(*)                                                     AS jobs_together,
       round(count(*) * 1.0 / (fa.n + fb.n - count(*)), 4)          AS jaccard,
       round(count(*) * 1.0 * any_value(n.n_jobs) / (fa.n * fb.n), 2) AS lift
FROM job_skills a
JOIN job_skills b ON a.job_id = b.job_id AND a.skill < b.skill
JOIN freq fa ON fa.skill = a.skill
JOIN freq fb ON fb.skill = b.skill
CROSS JOIN n
GROUP BY a.skill, b.skill, fa.n, fb.n
HAVING count(*) >= 50
ORDER BY jobs_together DESC;

-- 3. Median salary with vs without each skill (posts since 2022, annual USD midpoint) -----
CREATE OR REPLACE TABLE salary_by_skill AS
WITH paid AS (
    -- one row per company + title: a company reposting the same ad every month must not
    -- count as dozens of independent salary observations
    SELECT job_id, (salary_usd_min + salary_usd_max) / 2 AS salary_usd
    FROM jobs
    WHERE salary_usd_min IS NOT NULL AND posted_at >= DATE '2022-01-01' AND is_canonical
    QUALIFY row_number() OVER (PARTITION BY lower(company), lower(title) ORDER BY posted_at DESC) = 1
), skills AS (SELECT DISTINCT skill, category FROM job_skills)
SELECT k.skill, k.category,
       count(*) FILTER (WHERE s.job_id IS NOT NULL)                     AS n_with,
       count(*) FILTER (WHERE s.job_id IS NULL)                         AS n_without,
       round(median(p.salary_usd) FILTER (WHERE s.job_id IS NOT NULL))  AS median_with,
       round(median(p.salary_usd) FILTER (WHERE s.job_id IS NULL))      AS median_without,
       round(median(p.salary_usd) FILTER (WHERE s.job_id IS NOT NULL)
           - median(p.salary_usd) FILTER (WHERE s.job_id IS NULL))      AS premium_usd
FROM skills k
CROSS JOIN paid p
LEFT JOIN job_skills s ON s.job_id = p.job_id AND s.skill = k.skill
GROUP BY ALL
HAVING count(*) FILTER (WHERE s.job_id IS NOT NULL) >= 30
ORDER BY premium_usd DESC;

-- 4. Remote share by year and source ------------------------------------------------------
CREATE OR REPLACE TABLE remote_share AS
SELECT year(posted_at) AS year, source,
       count(*)                                                    AS posts,
       count(*) FILTER (WHERE is_remote)                           AS remote_posts,
       round(count(*) FILTER (WHERE is_remote) * 100.0 / count(*), 1) AS remote_pct
FROM jobs
GROUP BY ALL
ORDER BY year, source;

-- 5. How sources differ: role mix and top skills ------------------------------------------
CREATE OR REPLACE TABLE source_profile AS
WITH base AS (   -- compare like with like: only the last 12 months of each source
    SELECT * FROM jobs WHERE posted_at >= (SELECT max(posted_at) FROM jobs) - INTERVAL 365 DAY
), tot AS (SELECT source, count(*) AS n FROM base GROUP BY 1)
SELECT 'role_family' AS dimension, b.source, b.role_family AS value, count(*) AS jobs,
       round(count(*) * 100.0 / any_value(t.n), 1) AS share_pct
FROM base b JOIN tot t USING (source)
GROUP BY ALL
UNION ALL
SELECT 'skill', b.source, s.skill, count(*), round(count(*) * 100.0 / any_value(t.n), 1)
FROM base b JOIN job_skills s USING (job_id) JOIN tot t USING (source)
GROUP BY ALL
UNION ALL
SELECT 'seniority', b.source, b.seniority, count(*), round(count(*) * 100.0 / any_value(t.n), 1)
FROM base b JOIN tot t USING (source)
GROUP BY ALL
ORDER BY 1, 2, 4 DESC;

-- 6. Yearly roll-ups used by the report ---------------------------------------------------
CREATE OR REPLACE TABLE hn_yearly AS
SELECT year(posted_at) AS year,
       count(*)                                                             AS posts,
       count(DISTINCT date_trunc('month', posted_at))                       AS months,
       round(count(*) * 1.0 / count(DISTINCT date_trunc('month', posted_at))) AS posts_per_month,
       round(count(*) FILTER (WHERE is_remote) * 100.0 / count(*), 1)        AS remote_pct,
       round(count(*) FILTER (WHERE salary_usd_min IS NOT NULL) * 100.0 / count(*), 1) AS salary_disclosed_pct,
       round(median((salary_usd_min + salary_usd_max) / 2))                  AS median_salary_usd
FROM jobs WHERE source = 'hn'
GROUP BY 1 ORDER BY 1;

CREATE OR REPLACE TABLE salary_by_role AS
SELECT role_family, seniority, count(*) AS n,
       round(quantile_cont((salary_usd_min + salary_usd_max) / 2, 0.25)) AS p25,
       round(median((salary_usd_min + salary_usd_max) / 2))              AS median,
       round(quantile_cont((salary_usd_min + salary_usd_max) / 2, 0.75)) AS p75
FROM jobs
WHERE salary_usd_min IS NOT NULL AND posted_at >= DATE '2022-01-01' AND is_canonical
GROUP BY ALL HAVING count(*) >= 20
ORDER BY median DESC;

-- 7. How long listings stay open (needs several days of snapshots to become meaningful) ---
CREATE OR REPLACE TABLE listing_duration AS
SELECT source, count(*) AS jobs,
       round(avg(date_diff('day', first_seen, last_seen)), 1)  AS avg_days_seen,
       median(date_diff('day', first_seen, last_seen))         AS median_days_seen,
       count(DISTINCT last_seen)                               AS snapshot_days
FROM jobs WHERE source <> 'hn'
GROUP BY 1;
