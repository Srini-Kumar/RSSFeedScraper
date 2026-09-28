Multi-Source Entertainment RSS Feed Generator

An automated Python scraper that extracts movies, OTT releases, web series, and torrent titles from three sources — Times of India, 91Mobiles, and 1TamilMV — and publishes separate RSS feeds for each website, language, and category via GitHub Actions + GitHub Pages.
📡 Live RSS Feed URLs

Base URL: https://<your-username>.github.io/<repository-name>/
Times of India — Movies (per language)
Language	URL
Tamil	feed_toi_tamil.xml
Malayalam	feed_toi_malayalam.xml
Hindi	feed_toi_hindi.xml
English	feed_toi_english.xml
91Mobiles — OTT This Week (per language)
Language	URL
Tamil	feed_91mobiles_ott_tamil.xml
Malayalam	feed_91mobiles_ott_malayalam.xml
Hindi	feed_91mobiles_ott_hindi.xml
English	feed_91mobiles_ott_english.xml
91Mobiles — Web Series This Week (per language)
Language	URL
Tamil	feed_91mobiles_series_tamil.xml
Malayalam	feed_91mobiles_series_malayalam.xml
Hindi	feed_91mobiles_series_hindi.xml
English	feed_91mobiles_series_english.xml
1TamilMV — Latest Downloads
Feed	URL
1TamilMV	feed_1tamilmv.xml
📊 What Each Feed Contains
Times of India (Movies)

    Title, Poster Image, Rating, Genre, Duration, Release Date
    One feed per language (Tamil, Malayalam, Hindi, English)

91Mobiles OTT This Week

    Title, Poster Image, Language, Release Date, Description
    Filtered by language (Tamil, Malayalam, Hindi, English)
    One feed per language

91Mobiles Best Web Series (This Week)

    Title, Poster Image, Language, Release Date, Description
    Filtered by language and only items released within the last 7 days
    One feed per language

1TamilMV

    First 25 movie titles (title only)
    Single feed: feed_1tamilmv.xml

🛠️ Tech Stack

    Python 3.11 — requests, beautifulsoup4, lxml, feedgen
    GitHub Actions — Hourly Cron (0 * * * *)
    GitHub Pages — Static RSS hosting

⚙️ Deployment

    Push all files to a public GitHub repository.
    Go to Settings → Pages → Source: Deploy from a branch → main (/root).
    Go to Actions tab → manually trigger workflow to generate initial feeds.
    Feeds will auto-update every hour thereafter.

🔧 Feed Generation Logic

TOI (4 languages)           → 4 feeds: feed_toi_{lang}.xml91Mobiles OTT (4 langs)    → 4 feeds: feed_91mobiles_ott_{lang}.xml91Mobiles Series (4 langs) → 4 feeds: feed_91mobiles_series_{lang}.xml1TamilMV (25 titles)        → 1 feed:  feed_1tamilmv.xml                            ────────────────────                            Total: 13 RSS feeds (no combined/master feeds)