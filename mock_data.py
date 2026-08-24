"""
Mock dataset standing in for real Reddit/app-review data.

Deliberately mixes:
  - Cluster A (5 posts): losing track of recurring subscriptions/payments
  - Cluster B (4 posts): freelancers struggling to track time across clients/tools
  - Cluster C (3 posts): losing recipes saved as screenshots/videos across apps
  - Singletons (5 posts): one-off complaints that are topically "close enough"
    to tempt a sloppy summarizer into lumping them together, but are NOT the
    same underlying problem. These exist specifically to test whether the
    analyzer over-clusters.

Replace this module with a real data source later (e.g. reddit_client.py)
without touching analyzer.py or models.py.
"""

from models import Post

MOCK_POSTS: list[Post] = [
    # ---------- Cluster A: subscription/payment tracking ----------
    Post(
        id="p1", source="reddit", subreddit="personalfinance",
        title="Just found out I've been paying for 3 apps I forgot about",
        body="Checked my bank statement and found Headspace, a photo editor, and some "
             "cloud storage service I don't even use anymore. Together that's like $35/month "
             "wasted. I have no idea how many other subscriptions are quietly draining my account.",
    ),
    Post(
        id="p2", source="reddit", subreddit="frugal",
        title="How do you all keep track of subscriptions?",
        body="I swear every few months I find a new recurring charge I forgot to cancel. "
             "Free trials are the worst, you sign up, forget, and boom you're charged for a "
             "full year. Is there a good way to keep a running list?",
    ),
    Post(
        id="p3", source="reddit", subreddit="personalfinance",
        title="Got double charged because I forgot which email I used to sign up",
        body="I resubscribed to a streaming service not realizing my old account was still "
             "active under a different email. Now I'm paying for two accounts. I really need "
             "a single place that shows everything I'm subscribed to.",
    ),
    Post(
        id="p4", source="reddit", subreddit="anticonsumption",
        title="Cancelled 6 subscriptions today and felt real regret about how long I'd had them",
        body="Went through my card statement line by line for the first time in over a year. "
             "Found a meditation app, two streaming services I never use, and a subscription "
             "box I forgot I signed up for during a sale. There has to be a better way than "
             "manually scanning statements.",
    ),
    Post(
        id="p5", source="reddit", subreddit="personalfinance",
        title="Spreadsheet for tracking subscriptions isn't cutting it anymore",
        body="I built a spreadsheet to track my subscriptions but I never remember to update "
             "it when I sign up for something new, so it's always out of date and basically "
             "useless by the time I check it.",
    ),

    # ---------- Cluster B: freelancer time tracking across clients/tools ----------
    Post(
        id="p6", source="reddit", subreddit="freelance",
        title="Juggling timers across 4 different client tools is exhausting",
        body="One client wants me to log time in Toggl, another uses their own internal "
             "portal, a third just wants a weekly email summary. I end up guessing my hours "
             "for at least one client every single week because I forgot to start a timer.",
    ),
    Post(
        id="p7", source="reddit", subreddit="freelance",
        title="Undercharged a client by 6 hours because I lost track of time",
        body="I was deep in a project and completely forgot to track my hours for almost a "
             "full day. Ended up estimating and I'm pretty sure I lowballed it. This keeps "
             "happening because none of my tools talk to each other.",
    ),
    Post(
        id="p8", source="reddit", subreddit="digitalnomad",
        title="Anyone else hate having to reconstruct their timesheet at the end of the week?",
        body="I do consulting for 3 companies and by Friday I genuinely cannot remember which "
             "hours went to which client. I've tried sticky notes, a notes app, everything. "
             "It always falls apart by Wednesday.",
    ),
    Post(
        id="p9", source="reddit", subreddit="freelance",
        title="Losing money because time tracking across projects is such a mess",
        body="Between Slack calls, quick emails, and 'just a 5 minute favor' tasks for "
             "different clients, so much of my billable time just evaporates because I never "
             "logged it anywhere in the moment.",
    ),

    # ---------- Cluster C: recipes saved as screenshots/videos, hard to find later ----------
    Post(
        id="p10", source="reddit", subreddit="cooking",
        title="I have 200 recipe screenshots and can never find the one I want",
        body="My camera roll is a graveyard of recipe screenshots from Instagram and "
             "TikTok. When I actually want to cook something specific I remember seeing, "
             "I can never find it again. I've basically given up searching.",
    ),
    Post(
        id="p11", source="reddit", subreddit="mealprep",
        title="Saved a great pasta recipe from a TikTok and now it's gone",
        body="The account got deleted or the video got taken down, I don't even know. I "
             "didn't write down the ingredients because I figured I could just rewatch it "
             "later. Lesson learned, but this has happened to me at least 3 times now.",
    ),
    Post(
        id="p12", source="reddit", subreddit="cooking",
        title="Wish there was a way to actually organize recipes from social media",
        body="Between Pinterest boards, saved Instagram posts, and screenshots, my recipes "
             "are scattered across like 5 different places and none of them are searchable "
             "by ingredient or easy to browse when I'm standing in the kitchen deciding what "
             "to make.",
    ),

    # ---------- Singletons: topically adjacent but NOT the same recurring problem ----------
    Post(
        id="p13", source="reddit", subreddit="personalfinance",
        title="Bank flagged a legitimate purchase as fraud and locked my card for a week",
        body="I was traveling and bought something slightly unusual and my bank froze my "
             "card entirely. Took 6 days and 3 phone calls to get it unlocked. Completely "
             "different issue from subscriptions, just a rough fraud-detection experience.",
    ),
    Post(
        id="p14", source="reddit", subreddit="freelance",
        title="Client ghosted me after final delivery, still haven't been paid",
        body="Finished a big project two months ago, sent the invoice, and now the client "
             "has gone completely silent. Not a time-tracking issue, this is purely about "
             "chasing down payment after the work is already done.",
    ),
    Post(
        id="p15", source="reddit", subreddit="cooking",
        title="My oven runs 25 degrees hotter than the dial says",
        body="Finally bought an oven thermometer and realized my oven has been cooking "
             "everything too hot for years. Explains a lot of burnt edges. Not related to "
             "finding recipes, just a hardware calibration problem.",
    ),
    Post(
        id="p16", source="reddit", subreddit="digitalnomad",
        title="Visa renewal process for Portugal was way more confusing than expected",
        body="Spent an entire weekend trying to figure out which forms I needed and the "
             "official site contradicted itself twice. Eventually got it sorted through a "
             "local Facebook group. One-off bureaucratic headache, nothing to do with work "
             "tools.",
    ),
    Post(
        id="p17", source="reddit", subreddit="anticonsumption",
        title="Impulse-bought a $400 espresso machine and regret it",
        body="Saw an ad, bought it same day, now it's sitting on my counter barely used. "
             "This is just a personal impulse-spending story, not really about recurring "
             "subscriptions or tracking anything.",
    ),
]
