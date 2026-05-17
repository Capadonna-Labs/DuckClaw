# UI Design Patterns

This document contains descriptions and examples of various UI Design Patterns extracted from ui-patterns.com.

## Accordion Menu

**URL Validation:** https://ui-patterns.com/patterns/AccordionMenu

### Problem Summary
User needs to navigate among a websites main sections while still being able to quickly browse to the subsection of another.

### Solution
Each headline / section has a panel, which upon clicking can be expanded either vertically or horizontally into showing its subsections. Vertical Accordion menus are the most frequently used.
	The transition from showing no options of a headline to showing a headlines list of options can be done either with a page refresh or with a javascript DHTML animation.
	When one panel is clicked it is expanded, while other panels are collapsed.

### Rationale
Accordion menus are often used as a websites main navigation. In this way, it acts much like Navigation Tabs, as menu items are collapsed when a new panel is clicked. Where the Navigation Tabs are most often used horizontally, Accordion menus are most often used vertically.
Accordion menus can however also function quite well as sub-navigation for a specific section of a website.

### Usage Examples
Each headline / section has a panel, which upon clicking can be expanded either vertically or horizontally into showing its subsections. Vertical Accordion menus are the most frequently used.
	The transition from showing no options of a headline to showing a headlines list of options can be done either with a page refresh or with a javascript DHTML animation.
	When one panel is clicked it is expanded, while other panels are collapsed.

---

## Account Registration

**URL Validation:** https://ui-patterns.com/patterns/AccountRegistration

### Problem Summary
You wish to know who the active user is in order to provide personalized content or opportunities to conduct a purchase.

### Solution
Ask users to register an account in order to provide a personalized experience.  Let users register an account to allow saving information with your service, provide a personalized experienced, or give access to limited resources.
Common design flaws for registration and sign-in features include:

	Visibility: make sure the “Sign-in” and “Sign-Up” buttons” are clear, easy to see and easy to access. Don’t hide the “Sign-in” button/form.
	Call to Action: Draw attention to crucial operations such as Register new account Sign-in, and I forgot my password. Ensure your action buttons are appealing and encourage new users to join.
	Nudge: Exploit sign-up opportunity at key locations, don’t just rely on one point of action.
	Redundancy: Provide plenty of “Sign-In” buttons at key locations. Users often wait to the last moment to sign in. Key locations are points of action; for instance when the user wants to add a comment to a blog post.
	Complicated: Don’t frustrate users with complicated password requirements. The strength of the password you require needs to match the need for protection. A password policy that is too strict can hinder sign-up and may discourage potential customers.

You can make your account registration easier on your users including:

	Provide a simple and understandable  description of the requirements for usernames and passwords.
	Additionally, you might want to provide a password strength meter to provide instant feedback on how well the entered password meets the requirements instead of displaying an error message after the user has clicked the submit button.
	Similarly, you might also want to use AJAX to check for the availability of the username on every keystroke, so that the user does not need to submit the entire form several times before he is allowed entrance.
	When logging in, return to the page the user came from. If the point of action was submitting a comment to a blog post, redirect the user to the comment form after login.
	Consider incorporating a social sign in options such as “Facebook Login” into your website/application and avoid the entire new password paradigm entirely.

### Rationale
Account registration enables personalized and contextual content to be presented to authenticated users.
Account registration allows for remembering details about the user; product wish lists, preferences, interests, shipping and billing addresses, VAT number for billing purposes, and more.
Benefits of letting the users register an account with your site include:

	You know who is using your system
	You know how often they visit
	You know what they do on your site.
	You can store information your users might need later, such as billing info or wish lists for future purchases.
	You can use account registration to reserve special content from your regular users.
	You can differentiate prices, information displayed, and access rights depending on who the logged in user is.

### Usage Examples
Ask users to register an account in order to provide a personalized experience.  Let users register an account to allow saving information with your service, provide a personalized experienced, or give access to limited resources.
Common design flaws for registration and sign-in features include:

	Visibility: make sure the “Sign-in” and “Sign-Up” buttons” are clear, easy to see and easy to access. Don’t hide the “Sign-in” button/form.
	Call to Action: Draw attention to crucial operations such as Register new account Sign-in, and I forgot my password. Ensure your action buttons are appealing and encourage new users to join.
	Nudge: Exploit sign-up opportunity at key locations, don’t just rely on one point of action.
	Redundancy: Provide plenty of “Sign-In” buttons at key locations. Users often wait to the last moment to sign in. Key locations are points of action; for instance when the user wants to add a comment to a blog post.
	Complicated: Don’t frustrate users with complicated password requirements. The strength of the password you require needs to match the need for protection. A password policy that is too strict can hinder sign-up and may discourage potential customers.

You can make your account registration easier on your users including:

	Provide a simple and understandable  description of the requirements for usernames and passwords.
	Additionally, you might want to provide a password strength meter to provide instant feedback on how well the entered password meets the requirements instead of displaying an error message after the user has clicked the submit button.
	Similarly, you might also want to use AJAX to check for the availability of the username on every keystroke, so that the user does not need to submit the entire form several times before he is allowed entrance.
	When logging in, return to the page the user came from. If the point of action was submitting a comment to a blog post, redirect the user to the comment form after login.
	Consider incorporating a social sign in options such as “Facebook Login” into your website/application and avoid the entire new password paradigm entirely.

---

## Achievements

**URL Validation:** https://ui-patterns.com/patterns/Achievements

### Problem Summary
We are engaged by activities in which meaningful achievements are recognized

### Solution
Articulate what is possible. What challenges and desired behavior do you have in place and how are they linked to achievements? Achievements can help anchor the ambitions we want users to embrace. In gaming, achievements are shown through points, badges, and levels; in other contexts through promotions, memberships, privileges, and acquisitions. Consider providing social proof what has been achieved by similar peers.
	Provide appropriate challenges. Break down a larger goal into smaller and more easily obtainable wins that match the gradually rising skill level of your users as they go from one challenge to the next. A too hard challenge will leave users stressed, full of anxiety, and giving up. A too easy challenge will leave people bored and looking for something harder to try.
	Provide feedback. When a list of possible achievements are publicly accessible, achieving of each provide feedback on the users progress as to how much is left. Furthermore, achievements can communicate what is possible and what directions a user can take.

### Rationale
We are motivated by achievements of personal or social significance that represent appropriate challenges matching our gradually rising skill level as we go from one achievement to the other. Achievements help anchor what goals users should aspire to achieve and provide social proof what is obtainable for peers similar to us. In this way they allow for social comparison and can help increase our self-efficacy.
Why do achievements work?
There are several reasons why achievements work and ways in which they can help your product:

	Achievements anchor our expectations. When making decisions, we tend to rely, or anchor, heavily on the first information presented. This is called the anchoring effect. In this setting, achievements anchor what goals we should aspire to achieve. A too low goal might lead to ambitions not matching user capabilities and end in boredom where a too high and seemingly unobtainable goal will leave users stressed and full of anxiety. In this way, achievements can help communicate and anchor expectations about what are reasonable goals to aim for.
	Having goals increases self efficacy. Seeing proof of others who obtained trophies and other achievements communicates the idea that obtainment is possible2. It stirs our belief in our own efficacy  our ability to do something if we just try it. Of course, this requires that the goal seems appropriate to the skillset of your users and where they are in their learning journey.
	Completing goals are rewarding.  Completing a goal is a reward in itself and is a key motivational factor to drive people toward action. Especially when users are close to completion or reaching their goal.
	Goals creates commitment. When goals are clearly articulated and broken down into tasks, it increases chances that users will reach them as the commitment is more clear1. Can you further get users to publicly commit to the mission of achieving a goal, the power of the commitment gets stronger.
	Achievements provide feedback. When a list of possible achievements are publicly accessible, achieving of each provide feedback on the users progress as to how much is left. Furthermore, achievements can communicate what is possible and what directions a user can take.
	*Achievements trigger social proof. Both in the sense of showcasing the credibility and merits of an individual user, but also what achievements or goals are more obtainable than others. Social proof is our tendency to assume the actions of others in new or unfamiliar situations.
	Achievements trigger social comparisons. We seek objective information about our performance. When that information, or a suitable context to evaluate it in, is not there, we will seek to compare ourselves to meaningful others3. Achievements, trophies, and badges earned by other users is a convenient way to do this kind of benchmarking; if I can see that similar peers earned an achievement, I am more motivated to try it.

### Usage Examples
Articulate what is possible. What challenges and desired behavior do you have in place and how are they linked to achievements? Achievements can help anchor the ambitions we want users to embrace. In gaming, achievements are shown through points, badges, and levels; in other contexts through promotions, memberships, privileges, and acquisitions. Consider providing social proof what has been achieved by similar peers.
	Provide appropriate challenges. Break down a larger goal into smaller and more easily obtainable wins that match the gradually rising skill level of your users as they go from one challenge to the next. A too hard challenge will leave users stressed, full of anxiety, and giving up. A too easy challenge will leave people bored and looking for something harder to try.
	Provide feedback. When a list of possible achievements are publicly accessible, achieving of each provide feedback on the users progress as to how much is left. Furthermore, achievements can communicate what is possible and what directions a user can take.

---

## Activity Stream

**URL Validation:** https://ui-patterns.com/patterns/ActivityStream

### Problem Summary
The user wants to get an overview of recent actions in a system that are interesting from his or her perspective.

### Solution
Provide an overview of recent activity that is relevant to the user.
Allow users to catch up on recent updates with little time and effort invested. Activity streams are most often used to aggregate recent actions by individual or multiple users from the perspective of one user. They provide links to further explore the actor, the subject, or the activity itself.
The Activity Stream is a live feed, created by aggregating social activities in one place, for a user and their contacts. Social activities can vary greatly depending on the system. Popular activities are uploads (photos, videos, audio, and other files), comments, new friendship/follower relationships, bookmarks on del.icio.us or ma.gnolia, music on last.fm, posts from blogs, or even items in the feeds of facebook, friendfeed, and twitter. Every action a user does can be gathered into one stream.
An activity stream can either aggregate the actions of a single user or the actions interesting to a single user. The first is about only one user and the latter abut multiple users from the perspective of one user. Aggregating actions of a single user is often used on profile pages, where all actions the profiled user has done is aggregated into one place. Aggregating actions interesting to a single user aggregates all actions from the users friends and who he or she follows into one stream.
The details of an activity stream
Generally, the anatomy of an activity are one of these2:
Actor |verb| (object) [context]
Anders |tweeted| (Testing, testing) [via Tweetie]
Actor |verb| (object) {Indirect object} [context]
Anders |tweeted| (Testing, testing) {to Christian} [via Tweetie]
Aggregated activities
When multiple similar activities happen, they can beneficially be aggregated into story. A list like this

	David changed his profile picture
	Thomas changed his profile picture
	Ashley changed her profile picture

can be converted into this:

	David, Thomas, and Ashley changed their profile pictures

Verbs
Common verbs used in activities are: Likes, followed, commented, tagged, bought, posted, shared, and uploaded.

### Rationale
Activity streams allow for engagement. They expose users to the possible actions that can be taken on a site. At a glance, users can see what other people are doing and start experimenting themselves. In this sense, activity streams is an alternate form of navigation and discovery.
Activity streams are real-time, and thus put a focus on what is going on right now: They have timely relevance.
They allow users to stay in touch across the web in an open and emergent fashion.
As activity streams consists of many small bits of information. Bits of information that can be filtered, searched, and automated. They are a combination of quantitative small stories with qualitative attributes. However, the stories can be qualitative in nature like updating a status in facebook and the attributes can be quantitative such as the number of likes. Content that has value to the user can be produced by combining smaller bits of information, which in isolation does not have value.
Similarly, the large quantities of data can be used to predict what is more important for one user based on his or her past behavior.

### Usage Examples
Provide an overview of recent activity that is relevant to the user.
Allow users to catch up on recent updates with little time and effort invested. Activity streams are most often used to aggregate recent actions by individual or multiple users from the perspective of one user. They provide links to further explore the actor, the subject, or the activity itself.
The Activity Stream is a live feed, created by aggregating social activities in one place, for a user and their contacts. Social activities can vary greatly depending on the system. Popular activities are uploads (photos, videos, audio, and other files), comments, new friendship/follower relationships, bookmarks on del.icio.us or ma.gnolia, music on last.fm, posts from blogs, or even items in the feeds of facebook, friendfeed, and twitter. Every action a user does can be gathered into one stream.
An activity stream can either aggregate the actions of a single user or the actions interesting to a single user. The first is about only one user and the latter abut multiple users from the perspective of one user. Aggregating actions of a single user is often used on profile pages, where all actions the profiled user has done is aggregated into one place. Aggregating actions interesting to a single user aggregates all actions from the users friends and who he or she follows into one stream.
The details of an activity stream
Generally, the anatomy of an activity are one of these2:
Actor |verb| (object) [context]
Anders |tweeted| (Testing, testing) [via Tweetie]
Actor |verb| (object) {Indirect object} [context]
Anders |tweeted| (Testing, testing) {to Christian} [via Tweetie]
Aggregated activities
When multiple similar activities happen, they can beneficially be aggregated into story. A list like this

	David changed his profile picture
	Thomas changed his profile picture
	Ashley changed her profile picture

can be converted into this:

	David, Thomas, and Ashley changed their profile pictures

Verbs
Common verbs used in activities are: Likes, followed, commented, tagged, bought, posted, shared, and uploaded.

---

## Adaptable View

**URL Validation:** https://ui-patterns.com/patterns/AdaptableView

### Problem Summary
You want to let the sites presentation of content fit the specific needs of the user.

### Solution
Provide a mechanism to switch or alter the default style of a page so that it fits the specific needs of the user.
When catering to alternative browsers such as mobile phone browsers, the view to present can often be found looking at the incoming user agent. In this case, a manual mechanism to switch styles might seem obsolete, but it is good practice to allow access to all views of a site regardless of how the user is browsing it.
Provide a manual control to allow users to switch/alter the default style of a page so that it better fits their specific needs. It is for instance not all iPhone users who actually like to use tailored iPhone versions of websites instead of the full-featured browser version.
It is a good practice to allow for permanence of the users preferred configuration. This will prevent the user from having to make the same adjustment each time a page reloads.

### Rationale
By providing a mechanism to present different views of content to the user, you can tailor usability and the experience you want to give your users to their specific needs.

### Usage Examples
Provide a mechanism to switch or alter the default style of a page so that it fits the specific needs of the user.
When catering to alternative browsers such as mobile phone browsers, the view to present can often be found looking at the incoming user agent. In this case, a manual mechanism to switch styles might seem obsolete, but it is good practice to allow access to all views of a site regardless of how the user is browsing it.
Provide a manual control to allow users to switch/alter the default style of a page so that it better fits their specific needs. It is for instance not all iPhone users who actually like to use tailored iPhone versions of websites instead of the full-featured browser version.
It is a good practice to allow for permanence of the users preferred configuration. This will prevent the user from having to make the same adjustment each time a page reloads.

---

## Alternating Row Colors

**URL Validation:** https://ui-patterns.com/patterns/AlternatingRowColors

### Problem Summary
The user needs to visually separate similar looking rows in a table apart, in order to match the values of each row.

### Solution
To differentiate table rows from each other, a different shade is used as background color for every second row. Keep the difference between the two colors to a minimum to preserve a gentle feeling. The colors should be similar in value and low in saturation  the one should be slightly darker or lighter than the other. It is often seen that one of the two colors is the background color of the page itself.

### Rationale
The purpose of the shading in every second row is only to provide an visual aid for the every  users to follow a row from the left to the right and back again  without confusing one row with another. The purpose is not to drastically change the design of the table.
A side effect of shading every second row with an alternating color is however that the table will stand out from the rest of the page. The shading in this way boxes in the table.

### Usage Examples
To differentiate table rows from each other, a different shade is used as background color for every second row. Keep the difference between the two colors to a minimum to preserve a gentle feeling. The colors should be similar in value and low in saturation  the one should be slightly darker or lighter than the other. It is often seen that one of the two colors is the background color of the page itself.

---

## Anchoring

**URL Validation:** https://ui-patterns.com/patterns/Anchoring

### Problem Summary
We tend to rely too heavily on the first information presented

### Solution
One of the most used examples of price anchoring is probably the suggested retail price. When showing the regular price and the sale price together, the sale price is anchored to the regular price and thus seem like a cheap bargain  even when the sale price wouldnt have seem like a big deal without the comparison. A cheap price doesnt become a big deal unless we compare it with a more expensive price  or item. Whats even more: we are inherently bad at remembering what price we typically pay, even for our favorite items.

	Set the initial anchor. Present an initial anchor price or offer to influence subsequent negotiations in your favor.
	Anchor within an acceptable range. A high price makes all others seem cheaper as long as the high price is within an acceptable and plausible range. When anchored within an acceptable range, people tend to accept the anchor rather than start adjusting down.
	Experience weakens the effect. Anchoring is more effectful dealing with new concepts or objects and is weaker in effect dealing with individuals with higher cognitive ability or when dealing with those who have experience buying the product youre selling.

### Rationale
The first piece of information offered tend to automatically become the anchor from which subsequent judgments are made. Nothing is cheap or expensive by itself, but it could be, compared to something else. Anchoring can influence whether we find a product good or not – and in some cases whether we think it is fair to pay or to be paid for a product or service. People will anchor whether you intend for them to do so or not.
An initial value, the anchor, serves as a mental benchmark or starting point for estimating an unknown quantity. When first being presented with an anchor value, it is as if the anchor exerts a magnetic attraction, pulling estimates closer to itself. Anchoring works  even when the initial anchor doesnt represent a reasonable number.
By adding a high priced item to your list of products makes everything else near it look like a relative bargain. When we estimate a numerical value we tend to be susceptible to the power of suggestion. Any related value that we hear just before we make our estimate has a big statistical proven impact on what number were going to estimate. Even when warned beforehand about the persuasive powers of anchoring we cannot help but relate information presented alongside when we estimate whats a fair price or value1.
This is also the reason why its a good idea to get your number in first in a negotiation rather than letting your opponent name a number first

### Usage Examples
One of the most used examples of price anchoring is probably the suggested retail price. When showing the regular price and the sale price together, the sale price is anchored to the regular price and thus seem like a cheap bargain  even when the sale price wouldnt have seem like a big deal without the comparison. A cheap price doesnt become a big deal unless we compare it with a more expensive price  or item. Whats even more: we are inherently bad at remembering what price we typically pay, even for our favorite items.

	Set the initial anchor. Present an initial anchor price or offer to influence subsequent negotiations in your favor.
	Anchor within an acceptable range. A high price makes all others seem cheaper as long as the high price is within an acceptable and plausible range. When anchored within an acceptable range, people tend to accept the anchor rather than start adjusting down.
	Experience weakens the effect. Anchoring is more effectful dealing with new concepts or objects and is weaker in effect dealing with individuals with higher cognitive ability or when dealing with those who have experience buying the product youre selling.

---

## Appropriate Challenge

**URL Validation:** https://ui-patterns.com/patterns/Appropriate-challenge

### Problem Summary
The user needs appropriate challenges to remain engaged

### Solution
To keep users in flow we need to give them Appropriate challenges. If a challenge is too hard, the user is going to feel stress and anxiety. If the challenge is too easy, the user is going to feel bored. Both boredom and anxiety tend to lead to disengagement from the activity that was previously rewarding.
To design for appropriate challenges is to keep a careful balance between neither producing anxiety nor boredom. To keep users in the flow channel. It’s a careful dance keeping balance between the difficulty curve and the learning curve.
Users are most engaged, if they follow a roller-coaster pattern through the Flow Channel. It’s more fun in other words, if challenges sometimes seem too difficult  until our rising skill level flattens the curve. The ensuing mastery is also fun as we dominate the challenge or breeze through a task. But before it becomes old, the challenge level must rise again.

	Simplify it for beginners. Exposing a complicated or advanced user experience to a beginner will overwhelm them and possibly scare them away. Reduce complexity by hiding advanced options from direct sight so that novice users can concentrate on completion and immediate success.
	Allow advanced options. As users grow in skill level, they will want to explore more advanced options. Consider either showing shortcuts to more advanced features or designing an expert-only experience.
	Design for changes over time. Users evolve. Consider the contexts and skill-levels of your users and design appropriate challenges and experiences which suit them. Design for a sequence of events that progressively require an increased skill level.

### Rationale
Users are most engaged (in flow) when the difficulty of a challenge is matched with their skill level and is neither too hard or too easy. A too hard challenge will leave users stressed and full of anxiety. A too easy challenge will bore them. As a users skill level rises, a hard challenge becomes easy. Keep users in flow by ensuring a careful balance between the difficulty curve and the learning curve.
Consider the context of your users and design appropriate challenges and experiences which suit it. That is, design for changes over time. This is a radical break from the the standard usability approach, where everything is concentrated around making things as easy as possible. By designing for changes over time, you also concentrate on making things harder (more advanced) to do as users progress, to suit their growing skill level.
We’re in flow when we experience a task so positively that we do not allow ourselves to be diverted by distractions that don’t support the challenges and goals we are pursuing.
To keep users in flow we need to give them appropriate challenges. If a challenge is too hard, the user is going to feel stress and anxiety. If the challenge is too easy, the user is going to feel bored. Both boredom and anxiety tend to lead to disengagement from the activity that was previously rewarding.
To design for appropriate challenges is to keep a careful balance between producing neither anxiety nor boredom, to keep users in the flow channel.
When you think about appropriate challenges in your design, you are most often designing for a sequence of events that progressively require an increased skill level. In video games, the events are often represented by levels; in e-learning, by lessons within courses. To complete a challenge, it is necessary that the requisite learning takes place.

### Usage Examples
To keep users in flow we need to give them Appropriate challenges. If a challenge is too hard, the user is going to feel stress and anxiety. If the challenge is too easy, the user is going to feel bored. Both boredom and anxiety tend to lead to disengagement from the activity that was previously rewarding.
To design for appropriate challenges is to keep a careful balance between neither producing anxiety nor boredom. To keep users in the flow channel. It’s a careful dance keeping balance between the difficulty curve and the learning curve.
Users are most engaged, if they follow a roller-coaster pattern through the Flow Channel. It’s more fun in other words, if challenges sometimes seem too difficult  until our rising skill level flattens the curve. The ensuing mastery is also fun as we dominate the challenge or breeze through a task. But before it becomes old, the challenge level must rise again.

	Simplify it for beginners. Exposing a complicated or advanced user experience to a beginner will overwhelm them and possibly scare them away. Reduce complexity by hiding advanced options from direct sight so that novice users can concentrate on completion and immediate success.
	Allow advanced options. As users grow in skill level, they will want to explore more advanced options. Consider either showing shortcuts to more advanced features or designing an expert-only experience.
	Design for changes over time. Users evolve. Consider the contexts and skill-levels of your users and design appropriate challenges and experiences which suit them. Design for a sequence of events that progressively require an increased skill level.

---

## Archive

**URL Validation:** https://ui-patterns.com/patterns/Archive

### Problem Summary
All the items in a collection need to be organized in a chronological order.

### Solution
ist the items in your dataset in chronological order and provide suitable headlines to match the amount of items. If you for instance have 10 items per year, it does not make much sense to partition these 10 items into months. If you have 100 items a year, but also have months without any items, it might not make sense to list all months.
Either you can provide links to pages that shows all items per time period, or simply make a list of links to each item directly on the main archive page.

### Rationale
Use the archive pattern when it makes sense to list items in chronological order. Listing items in an archive format, makes it easy for the user to explore how a website has evolved over time and what has influenced the most current items.

### Usage Examples
ist the items in your dataset in chronological order and provide suitable headlines to match the amount of items. If you for instance have 10 items per year, it does not make much sense to partition these 10 items into months. If you have 100 items a year, but also have months without any items, it might not make sense to list all months.
Either you can provide links to pages that shows all items per time period, or simply make a list of links to each item directly on the main archive page.

---

## Article List

**URL Validation:** https://ui-patterns.com/patterns/ArticleList

### Problem Summary
The user needs guidance in finding editorial content of interest, which hierarchical navigation alone does not accomplish.

### Solution
An article lists is a great means of communicating for inspiration. It allows the user to quickly scan a list of articles that appeal or interest them.
When designing a good article list, there are several things you should take into consideration. Consider these design tips wisely, as overdoing them may trap you into committing some of the common design mistakes listed later in this pattern.
Design tips for designing great article lists
Dont over-design it: scanning is the main feature
The main purpose of the article list is to lure users to click on a story  so let them find one that they find interesting! One of your proudest objectives as a designer should be to get out of the way and let the user perform his or her task. The interface you design should afford scanning.
Too many ornaments and other unnecessary design elements hinder scanning. They have no other purpose than showing off.
Longer lists are good  when they are scannable
Pagination is overrated for two reasons:

	From the world of content to the world of navigation. Every time the user needs to use pagination to view more stories, he or she is pulled from the world of content to the world of navigation. The user is then no longer thinking about what stories they should read, but about how to find more to read. Using pagination creates a natural pause that lets the user re-evaluate if he or she wants to keep going or leave the site.
	Pagination numbers have no meaning. What does page 2, 3, or 4 mean? Its an abstract construction without root in anything real. For the user, being on page 2, 3, or 4 only indicates the inability to find anything interesting on page 1. Being on page 4 is a reminder of a lengthy website visit without finding anything of value. Instead, find a meaningful way to group articles: by week, month, year, category, tag, or by alphabet. Long lists are not a problem if they are scannable.

Long lists are not bad  as long as you can scan it easily and without effort.
Setting the scene with category labels
Category labels set the scene for what the user can expect. They communicate what the title of the article sometimes can’t which helps set the context of the title.
An article with the title Chanel goes crazy can have several different meanings. If the article is about Chanels last economic quarter, the title possibly conveys a rising crisis for the company, however if the article is about Chanels new designer collection, the meaning of the title is totally different.
In this way, the category label help set the users expectations for what is to be found behind the link. By labelling the story with either Fashion or Financial news, the correct meaning of the title is set in stone.
In the example below, the category label Movies let us know that the interview with Alexander Olch is about his new movie and the category label Literature lets us know that the picture with roller-skates is not actually about the rollerskating sport.

Listing related articles
On news sites, there are often many articles about a single subject. News is published in fragments as it comes in. To accommodate for this, many news sites not only display the main article on the front page, but also list related article to the subject in the near vicinity (most often below).
There are many aspects of a story which different people find interesting. If the main story will not catch the attention of a specific reader, there is a good chance another article on the same subject will.
Also, the list of articles on the same subject works as a great starting point for exploring the full story, and thus provides a good opportunity to increase the pages per visit.

At the Danish television company, TV2, the main article is followed by the a list of the next 3 articles from the same category.
Comment count as an indicator for interestedness
If an article is well commented, we we are lead to believe that it must be a more interesting read than articles with less comments. This effect is called social proof. We judge the popularity of something by the actions of others.
If you have a high comment activity on your site, listing comment count can help people stick around: “this must be an interesting site as people keep on commenting”. If your site has little or no comments on articles, you will communicate the opposite by showing comment count on article lists.
Include the author when your articles are opinionated
Everything is about the context. Always! Consider what kind of articles you are presenting. The author is relevant to an article teaser if it is opinionated  just like comment count is relevant to an article teaser if there are lots of them.

Highlight as featured article
If you want to attract attention to articles you believe will interest a lot of people, or that you put a lot of work into (the first is way more important), it can be a good idea to find a way to highlight the article.
One kind of highlighting is with an attached label in bright colors, another is changing the background color of the article list item. A third option is to find a prominent position for the article: e.g. at the top of the list with a larger thumbnail image.
Remember the call out
Remember to call out for action! Much has been said about the old-school click here call out, but whoever used it was on to half of the truth. The bad thing about click here is that it does not set expectations: what is going to happen when I click on it?. The good thing about click here is that it tells people what they should do. It calls out for action and does not require the user to think.
To get the call out right, you need to set expectations. If the user is taken to watch a video, then have a link saying watch the video. If you print out the first paragraph of text, then have a link that says read more.
You can also include call-outs in parts of the teaser other than just the text link. On video teasers a play icon placed over a thumbnail picture work great.

CNN.com has a great combination of video stories and regular text stories in this front page article list.
Common pitfalls of article list design
No visual difference between headline and subheading.
The visual hierarchy between the elements of an article teaser is important. For scanning purposes, the shorter heading affords better scanning than the subheading does. When the visible difference between the header and the subheader is too little, the user has to spend unnecessary energy on decoding which is which.
Forgetting to make everything a link
Make sure that the user can click on any part of the article teaser to go to the article itself: title, image, description, comment count, and call out. People are used to being able to click anywhere to go where they want.
Showing comment count when there are none
If your site does not have much comment activity, you will communicate that you have a boring site with unengaged users if you list the comment count for a bunch of articles with no comments.
The elements of an article list item
For an article list to work, you must provide a series of information for it to be useful. As always, everything depends on the context. If your articles are opinionated and more editorial than they are a news story, then the author is an important part. If you have different types of content on your site (news stories, quizzes, battles, etc.), then you would want to label your articles accordingly so that you set expectations.
Regardless of the context, there seems to be some details that are always important:

	Title the article
	Short description
	Publication date
	Call out to action (read more, continue reading, see more, etc.)

A series of details that are common, but are not present in all lists.

	Category label
	Thumbnail image
	Comment count
	Picture count (in gallery)
	Author

### Rationale
On a website delivering editorial content, the article teaser is one of the most important design elements besides the design of the article itself. The article teaser is part of an article list, and its main purpose to lure visitors to keep on browsing.
The most pure form of article lists is seen on magazine and news websites, but the convention is also relevant to all other sites trying to tease another click out of the visitor.

### Usage Examples
An article lists is a great means of communicating for inspiration. It allows the user to quickly scan a list of articles that appeal or interest them.
When designing a good article list, there are several things you should take into consideration. Consider these design tips wisely, as overdoing them may trap you into committing some of the common design mistakes listed later in this pattern.
Design tips for designing great article lists
Dont over-design it: scanning is the main feature
The main purpose of the article list is to lure users to click on a story  so let them find one that they find interesting! One of your proudest objectives as a designer should be to get out of the way and let the user perform his or her task. The interface you design should afford scanning.
Too many ornaments and other unnecessary design elements hinder scanning. They have no other purpose than showing off.
Longer lists are good  when they are scannable
Pagination is overrated for two reasons:

	From the world of content to the world of navigation. Every time the user needs to use pagination to view more stories, he or she is pulled from the world of content to the world of navigation. The user is then no longer thinking about what stories they should read, but about how to find more to read. Using pagination creates a natural pause that lets the user re-evaluate if he or she wants to keep going or leave the site.
	Pagination numbers have no meaning. What does page 2, 3, or 4 mean? Its an abstract construction without root in anything real. For the user, being on page 2, 3, or 4 only indicates the inability to find anything interesting on page 1. Being on page 4 is a reminder of a lengthy website visit without finding anything of value. Instead, find a meaningful way to group articles: by week, month, year, category, tag, or by alphabet. Long lists are not a problem if they are scannable.

Long lists are not bad  as long as you can scan it easily and without effort.
Setting the scene with category labels
Category labels set the scene for what the user can expect. They communicate what the title of the article sometimes can’t which helps set the context of the title.
An article with the title Chanel goes crazy can have several different meanings. If the article is about Chanels last economic quarter, the title possibly conveys a rising crisis for the company, however if the article is about Chanels new designer collection, the meaning of the title is totally different.
In this way, the category label help set the users expectations for what is to be found behind the link. By labelling the story with either Fashion or Financial news, the correct meaning of the title is set in stone.
In the example below, the category label Movies let us know that the interview with Alexander Olch is about his new movie and the category label Literature lets us know that the picture with roller-skates is not actually about the rollerskating sport.

Listing related articles
On news sites, there are often many articles about a single subject. News is published in fragments as it comes in. To accommodate for this, many news sites not only display the main article on the front page, but also list related article to the subject in the near vicinity (most often below).
There are many aspects of a story which different people find interesting. If the main story will not catch the attention of a specific reader, there is a good chance another article on the same subject will.
Also, the list of articles on the same subject works as a great starting point for exploring the full story, and thus provides a good opportunity to increase the pages per visit.

At the Danish television company, TV2, the main article is followed by the a list of the next 3 articles from the same category.
Comment count as an indicator for interestedness
If an article is well commented, we we are lead to believe that it must be a more interesting read than articles with less comments. This effect is called social proof. We judge the popularity of something by the actions of others.
If you have a high comment activity on your site, listing comment count can help people stick around: “this must be an interesting site as people keep on commenting”. If your site has little or no comments on articles, you will communicate the opposite by showing comment count on article lists.
Include the author when your articles are opinionated
Everything is about the context. Always! Consider what kind of articles you are presenting. The author is relevant to an article teaser if it is opinionated  just like comment count is relevant to an article teaser if there are lots of them.

Highlight as featured article
If you want to attract attention to articles you believe will interest a lot of people, or that you put a lot of work into (the first is way more important), it can be a good idea to find a way to highlight the article.
One kind of highlighting is with an attached label in bright colors, another is changing the background color of the article list item. A third option is to find a prominent position for the article: e.g. at the top of the list with a larger thumbnail image.
Remember the call out
Remember to call out for action! Much has been said about the old-school click here call out, but whoever used it was on to half of the truth. The bad thing about click here is that it does not set expectations: what is going to happen when I click on it?. The good thing about click here is that it tells people what they should do. It calls out for action and does not require the user to think.
To get the call out right, you need to set expectations. If the user is taken to watch a video, then have a link saying watch the video. If you print out the first paragraph of text, then have a link that says read more.
You can also include call-outs in parts of the teaser other than just the text link. On video teasers a play icon placed over a thumbnail picture work great.

CNN.com has a great combination of video stories and regular text stories in this front page article list.
Common pitfalls of article list design
No visual difference between headline and subheading.
The visual hierarchy between the elements of an article teaser is important. For scanning purposes, the shorter heading affords better scanning than the subheading does. When the visible difference between the header and the subheader is too little, the user has to spend unnecessary energy on decoding which is which.
Forgetting to make everything a link
Make sure that the user can click on any part of the article teaser to go to the article itself: title, image, description, comment count, and call out. People are used to being able to click anywhere to go where they want.
Showing comment count when there are none
If your site does not have much comment activity, you will communicate that you have a boring site with unengaged users if you list the comment count for a bunch of articles with no comments.
The elements of an article list item
For an article list to work, you must provide a series of information for it to be useful. As always, everything depends on the context. If your articles are opinionated and more editorial than they are a news story, then the author is an important part. If you have different types of content on your site (news stories, quizzes, battles, etc.), then you would want to label your articles accordingly so that you set expectations.
Regardless of the context, there seems to be some details that are always important:

	Title the article
	Short description
	Publication date
	Call out to action (read more, continue reading, see more, etc.)

A series of details that are common, but are not present in all lists.

	Category label
	Thumbnail image
	Comment count
	Picture count (in gallery)
	Author

---

## Authority Bias

**URL Validation:** https://ui-patterns.com/patterns/Authority

### Problem Summary
We have a strong tendency to comply with authority figures

### Solution
When determining who is an authority, we have surprisingly low standards and respond instinctively. A blue uniform represents a policeman who should be obeyed, a white lab coat and stethoscope represents a doctor whos advice we should consider, and a man in a business suit must represent a respected business man whos opinions we should listen to.
Cialdini found three significant symbols of authority that will reliably trigger our compliance in the absence of the genuine substance of authority: titles, clothes, and trappings (jewelry, cars, etc.)1.
Communicate authority
Communicate a sense of authority to your users by displaying appropriate credentials. List certifications, awards, or prominent customer testimonials. Associate yourself with authority figures by connecting their well-known face with your product.
Choose an authority figure depending on your business, who you want to influence, and how you want to influence them. Here are a few of examples:

	Use prominent athletes if you want to sell the products they use.
	Use doctors and nurses on health related websites.
	Use famous chefs if you want to sell food.

Study who represent authority in your field and in what way your users will comply with their message.
You however dont have to associate yourself with authority figures to communicate authority. Act like one yourself! Speak with confidence, lead discussions, blog, post videos, or find another way of establishing yourself or your company as an authority figure.

### Rationale
Authority bias is a cognitive bias that leads people to attribute greater accuracy and credibility to the opinions of an authority figure, regardless of the actual content of their claims. This bias can occur in various contexts, including decision-making processes, where individuals may disproportionately weigh the opinions of experts or leaders. It is influenced by societal norms and cultural conditioning, which teach individuals to respect and follow the guidance of those perceived as authorities.
This bias is not limited to interactions with recognized experts or leaders but can also manifest in situations where an individual appears authoritative due to their demeanor, attire, or the context in which they are presenting information. For example, someone wearing a lab coat or a uniform may be perceived as more knowledgeable or trustworthy, even if they have no expertise in the subject matter they are discussing.
Authority bias can lead to a number of consequences, both positive and negative. On the positive side, it can facilitate efficient decision-making when it encourages people to defer to experts in complex or specialized fields where they lack knowledge. However, it can also lead to negative outcomes, such as the uncritical acceptance of flawed ideas, obedience to harmful directives, or the perpetuation of misinformation. In extreme cases, authority bias can contribute to the development of cults of personality, where individuals are followed or idolized to a harmful extent.
Identifying with Authority Figures
People, who identify with authority figures, trust their taste and often believe that it fits their own  or at least they wish it did. If you have experts on your team, or if the people you work with are in some way authorities, then be sure to show them off to lend credibility to the product you sell.
We have a sense of duty to authority that makes us unable to defy their wishes. Authority help define the role we take upon ourselves and the roles we put on others. If an authority figure is seen as a teacher, we put on the learner or student role. If a policeman approaches us we take on the role as a suspect or informer.
We rarely agonize over the pros and cons that authority demands. With little or no conscious deliberation, we see information from a recognized authority as a valuable shortcut for deciding how to act in a situation. Authority positions speak of superior access to information and power, why it makes sense to comply with the wishes of properly constituted authorities.
Once a legitimate authority has given an order, subordinates stop thinking in the situation and start reacting. Often the appearance of authority is enough  we dont always need to provide real authority. A uniform or famous face can do. We are often as vulnerable to the symbols of authority as to the substance.

### Usage Examples
When determining who is an authority, we have surprisingly low standards and respond instinctively. A blue uniform represents a policeman who should be obeyed, a white lab coat and stethoscope represents a doctor whos advice we should consider, and a man in a business suit must represent a respected business man whos opinions we should listen to.
Cialdini found three significant symbols of authority that will reliably trigger our compliance in the absence of the genuine substance of authority: titles, clothes, and trappings (jewelry, cars, etc.)1.
Communicate authority
Communicate a sense of authority to your users by displaying appropriate credentials. List certifications, awards, or prominent customer testimonials. Associate yourself with authority figures by connecting their well-known face with your product.
Choose an authority figure depending on your business, who you want to influence, and how you want to influence them. Here are a few of examples:

	Use prominent athletes if you want to sell the products they use.
	Use doctors and nurses on health related websites.
	Use famous chefs if you want to sell food.

Study who represent authority in your field and in what way your users will comply with their message.
You however dont have to associate yourself with authority figures to communicate authority. Act like one yourself! Speak with confidence, lead discussions, blog, post videos, or find another way of establishing yourself or your company as an authority figure.

---

## Autocomplete

**URL Validation:** https://ui-patterns.com/patterns/Autocomplete

### Problem Summary
The user needs recognition aided search when performing search tasks that are difficult to remember or easily mistyped.

### Solution
Suggest possible matches for a search as users are typing.
The Autocomplete pattern is a predictive, recognition based mechanism used to assist users when searching. An autocomplete search field presents items which match the users input as they type. As the user types in more text into the search field, the list of matching items is narrowed down.
The list of matching items must allow users to select items using input devices such as keyboard arrow navigation, touch and mouse click. This allows the user to quickly select the term without having to type out the entire term. The patterns name comes from the notion that the system completes your search. Limit the number of matching items to display when working with large dataset. A standard limit is 10 matching items.
Find a maximum number of matching items to display when the matching data set is in the hundreds, thousands, or millions. A standard limit seems to be to present a maximum 10 matching items.
Order matching items by relevance with the most relevant or likely match at the top of the list. This will allow the user to quickly select his or her match.
Some autocomplete implementations group matching items into categories. On apple.com for instance, matches are organized by groups.
Implementation details
The autocomplete pattern is used in combination with a standard input text box that is labelled to match the users expectation of what field will be searched against1.
As the user types in data, a list of suggested items that match the inputted data is displayed. As more text is inputted, the displayed list is updated to matching the updated query  narrowing down matching items.
The list of suggested items is most often displayed directly beneath the input text box and has a width that matches the width of the text box.
It may be appropriate to highlight what part of a suggested item that matches what has been inputted. Example: “Amorphous”.
Allow the user to cancel the suggested items list by pressing the ESC key. Pressing the ESC key causes the suggested items list to close, however typing in more characters after pressing the ESC key will restart the autocompletion behaviour.

### Rationale
The Autocomplete pattern allows faster input, reduces the number of keystrokes needed, prevents typing errors, and provides feedback on the validity of what is being entered. It also allows designers to include longer lists for users to choose from without taking up extra screen real estate.
Autocompletion and search suggestions save the user keystrokes by matching a users query with potential matches that are displayed as the query is being typed.
It reduces the number of keystrokes and thus allows for faster data input. Tiresome, long, and complicated queries such as email addresses or airport names, can be found and selected with only a few keystrokes.
Additional formatting of a search suggestion can help remove ambiguity. If I am searching for an airport in London, extra formatting can tell me whether I am selecting Heathrow or Standsted airports.
Autocompletion provides a feedback loop that continually lets the user narrow in on the correct choice.
The cognitive burden of remembering an exact text-phrase is made easier, as the user can use the autocomplete pattern to only type in details that he or she remembers. If a user is searching for an email that he can only remember the domain name of, he or she can simply enter the domain name where-after all emails with that domain name is presented for selection.
The autocomplete pattern relies on the principle of recognition over recall. Instead of having to recall a full and exact text query, the user can start typing in parts of the query he or she recalls, and in turn rely on recognition to select the best match.

### Usage Examples
Suggest possible matches for a search as users are typing.
The Autocomplete pattern is a predictive, recognition based mechanism used to assist users when searching. An autocomplete search field presents items which match the users input as they type. As the user types in more text into the search field, the list of matching items is narrowed down.
The list of matching items must allow users to select items using input devices such as keyboard arrow navigation, touch and mouse click. This allows the user to quickly select the term without having to type out the entire term. The patterns name comes from the notion that the system completes your search. Limit the number of matching items to display when working with large dataset. A standard limit is 10 matching items.
Find a maximum number of matching items to display when the matching data set is in the hundreds, thousands, or millions. A standard limit seems to be to present a maximum 10 matching items.
Order matching items by relevance with the most relevant or likely match at the top of the list. This will allow the user to quickly select his or her match.
Some autocomplete implementations group matching items into categories. On apple.com for instance, matches are organized by groups.
Implementation details
The autocomplete pattern is used in combination with a standard input text box that is labelled to match the users expectation of what field will be searched against1.
As the user types in data, a list of suggested items that match the inputted data is displayed. As more text is inputted, the displayed list is updated to matching the updated query  narrowing down matching items.
The list of suggested items is most often displayed directly beneath the input text box and has a width that matches the width of the text box.
It may be appropriate to highlight what part of a suggested item that matches what has been inputted. Example: “Amorphous”.
Allow the user to cancel the suggested items list by pressing the ESC key. Pressing the ESC key causes the suggested items list to close, however typing in more characters after pressing the ESC key will restart the autocompletion behaviour.

---

## Blank Slate

**URL Validation:** https://ui-patterns.com/patterns/BlankSlate

### Problem Summary
The user wants to get started using the application but needs guidance in the form of an example of how the application will look, feel and behave when in full function and filled with data.

### Solution
Comfort, guide, or encourage users when there is no content to show.
Although Blank Slates arent typical, they are important opportunities for good design to avoid user disappointment or confusion. Make sure users feel safe and know what to do next when they use your product for the first time or have cleared all content.
Give the user an impression of how the system will look once filled with data   or guide and encourage them to start filling it with data. You can present the user with several kinds of helpful information on a blank slate:

	Show a sample screenshot of how the page will look once filled up with content,
	insert quick tutorials and help texts,
	explain the best ways to get started,
	ask questions the first-time user will ask: What is this? What do I do now?, and
	set expectations to help reduce frustration, intimidation, and overall confusion.

(Source: Getting Real by 37signals)

### Rationale
The blank slate is generally the first screen the user is presented with when they start something new in an application. It can the screen they are directed to after creating an account or the first screen they see when using part of an application they haven’t used before. The blank slate tells the user what the page they are on will look like, once it has eventually been filled with content. Creating a blank slate sets the user’s expectations for your service.
New users are often intimidated by empty screens with little or no guidance. Guiding users with a prepopulated starting state is the best way to establish trust and gain understanding.
Make sure the first impression the user gets of your web application is positive. Let them know why they should stick around.

### Usage Examples
Comfort, guide, or encourage users when there is no content to show.
Although Blank Slates arent typical, they are important opportunities for good design to avoid user disappointment or confusion. Make sure users feel safe and know what to do next when they use your product for the first time or have cleared all content.
Give the user an impression of how the system will look once filled with data   or guide and encourage them to start filling it with data. You can present the user with several kinds of helpful information on a blank slate:

	Show a sample screenshot of how the page will look once filled up with content,
	insert quick tutorials and help texts,
	explain the best ways to get started,
	ask questions the first-time user will ask: What is this? What do I do now?, and
	set expectations to help reduce frustration, intimidation, and overall confusion.

(Source: Getting Real by 37signals)

---

## Breadcrumbs

**URL Validation:** https://ui-patterns.com/patterns/Breadcrumbs

### Problem Summary
The user needs to know their location in the websites hierarchical structure in order to possibly browse back to a higher level in the hierarchy.

### Solution
Reveal the user’s hierarchical location and provide links to higher levels.

	Show the labels of the sections in the hierarchical path that lead to the current page being viewed.
	Each label is a link to a section.
	The label of the current page is at the end of the breadcrumb and is not linked.
	Each label is separated with a special character. Popular characters are  (raquo;) or .
	The separating characters and the spaces between the links and the labels are not linked.
	The labels of each section preferably match the titles of that section.

### Rationale
Breadcrumbs serve as an effective visual aid, indicating the location of the user within the website’s hierarchy, making them a great source of contextual information for landing pages. Also, breadcrumbs allow for easy navigation to higher-level pages.

	Breadcrumbs inform users of their location in relation to the entire sites hierarchy.
	The structure of the website is more easily understood when it is laid out in a breadcrumb than if it is put into a menu.
	Breadcrumbs take up minimal space and even though not all users use them, they still hint the structure of the website and the current location of the page in question.
	The term ‘breadcrumb’ is deceptive, as it implies the history of how the user got to that page. A more correct term would describe the current location’s place in the hierarchy of the website.

### Usage Examples
Reveal the user’s hierarchical location and provide links to higher levels.

	Show the labels of the sections in the hierarchical path that lead to the current page being viewed.
	Each label is a link to a section.
	The label of the current page is at the end of the breadcrumb and is not linked.
	Each label is separated with a special character. Popular characters are  (raquo;) or .
	The separating characters and the spaces between the links and the labels are not linked.
	The labels of each section preferably match the titles of that section.

---

## Calendar Picker

**URL Validation:** https://ui-patterns.com/patterns/CalendarPicker

### Problem Summary
The user wants to find or submit information based on a date or date range

### Solution
The calendar picker is activated in a variety of ways:

	When clicking a link prompting for selecting a date
	When selecting an field for inputting a date
	When clicking a calendar icon most often placed next to the field used for inputting a date

On activation, a box with a month-calendar is displayed on the current page, prompting the user to select a date in the box. It is most common to only show one month, but some interfaces show up to 3 month calendars next to each other to ease the click-burden of the user and provide a better overview.
Shortcuts
The month-box calendar comes with several different shortcuts:

	Select a date
	Go to the previous/next month
	Go to the previous/next year
	Go to today (Especially important when todays date is not the default)
	Close the calendar picker

Locking-in the period of selection
For some interfaces, it makes sense to not allow the selection of certain dates. An example often used is to only make it possible to select banking days, days in the future, or days within the few forthcoming months.
Two ways of inputting data: speedy and easy
When designing for efficiency in web application, an area that often gets little attention is the contexts of input. On most desktop computers the most common way of inputting data is via keyboard or mouse. On mobile devices touch, keyboard and camera are the most common input methods.
Using a calendar picker is an easy way of inputting a date. But also consider a quick and effortless way to input a date – one were the user does not need to switch between input devices but can rather accomplish their task with a single input device.
For accommodating text inputs, consider using the Forgiving Format pattern to lessen input errors.
Good defaults
Use the Good defaults pattern to achiee better data and spelling accuracy on input by pre-selecting appropriate dates.
The defaults you pre-select will depend on the context but will most often be the current date or time. However, If you were designing a public transport route planner, you might default the start time to a half hour from now, as most travellers won’t be starting their journey right away when searching for a fare.
Check date range validity
If the user is selecting a date range, it is good practice to never let end-date be before the start date. That means listening to the start-date for changes and changing the end-date if the start date is set to anything bigger.
Display complete weeks
Display complete weeks, even when a month does not begin at the end of the week. Grey out visible dates from previous and next months, but be sure they are still selectable.
Make link targets big
Make sure that link targets are big and thus easy to click on.

### Rationale
The calendar picker is a familiar graphical interface that is commonly understood among users. It helps the user easily choose a date or date range for use in submitting information or filtering data.

### Usage Examples
The calendar picker is activated in a variety of ways:

	When clicking a link prompting for selecting a date
	When selecting an field for inputting a date
	When clicking a calendar icon most often placed next to the field used for inputting a date

On activation, a box with a month-calendar is displayed on the current page, prompting the user to select a date in the box. It is most common to only show one month, but some interfaces show up to 3 month calendars next to each other to ease the click-burden of the user and provide a better overview.
Shortcuts
The month-box calendar comes with several different shortcuts:

	Select a date
	Go to the previous/next month
	Go to the previous/next year
	Go to today (Especially important when todays date is not the default)
	Close the calendar picker

Locking-in the period of selection
For some interfaces, it makes sense to not allow the selection of certain dates. An example often used is to only make it possible to select banking days, days in the future, or days within the few forthcoming months.
Two ways of inputting data: speedy and easy
When designing for efficiency in web application, an area that often gets little attention is the contexts of input. On most desktop computers the most common way of inputting data is via keyboard or mouse. On mobile devices touch, keyboard and camera are the most common input methods.
Using a calendar picker is an easy way of inputting a date. But also consider a quick and effortless way to input a date – one were the user does not need to switch between input devices but can rather accomplish their task with a single input device.
For accommodating text inputs, consider using the Forgiving Format pattern to lessen input errors.
Good defaults
Use the Good defaults pattern to achiee better data and spelling accuracy on input by pre-selecting appropriate dates.
The defaults you pre-select will depend on the context but will most often be the current date or time. However, If you were designing a public transport route planner, you might default the start time to a half hour from now, as most travellers won’t be starting their journey right away when searching for a fare.
Check date range validity
If the user is selecting a date range, it is good practice to never let end-date be before the start date. That means listening to the start-date for changes and changing the end-date if the start date is set to anything bigger.
Display complete weeks
Display complete weeks, even when a month does not begin at the end of the week. Grey out visible dates from previous and next months, but be sure they are still selectable.
Make link targets big
Make sure that link targets are big and thus easy to click on.

---

## Captcha

**URL Validation:** https://ui-patterns.com/patterns/Captcha

### Problem Summary
The application needs to verify that the data submitted originates from an actual human and not a robot.

### Solution
The most popular form of Captchas are images that represent letters and numbers inside. The user is prompted to write in a separate form field what the image reads in a separate form field. To prevent spammers from using OCR software to read the image, the image is manipulated in different ways, which makes it hard for computers while maintaining readability for humans.
If the user succeeds in typing what the image says, his content is posted to the website. If not, the action will be refused. It is common to allow a number of tries to enter the captcha text, as some captcha images are even unreadable to humans due to the strong image manipulation is has been exposed to.

### Rationale
Captchas are short for Completely Automated Public Turing test to tell Computers and Humans Apart. The whole idea behind Captchas is to distinguish humans from computers letting the user perform an action a computer cant. A captcha is a simple Turing test.
There is a fine line between making a captcha unrecognizable for OCR scanners and still readable for human beings. Readability for the human has to come first. Other problems with implementing captchas to protect your website include a lock-out from visually impaired users as they cant use voice software to speak what the captcha reads.
Other forms of protection from malicious spammers are asking questions like what is 2 + 3 or what is two plus three or using voice captchas,

### Usage Examples
The most popular form of Captchas are images that represent letters and numbers inside. The user is prompted to write in a separate form field what the image reads in a separate form field. To prevent spammers from using OCR software to read the image, the image is manipulated in different ways, which makes it hard for computers while maintaining readability for humans.
If the user succeeds in typing what the image says, his content is posted to the website. If not, the action will be refused. It is common to allow a number of tries to enter the captcha text, as some captcha images are even unreadable to humans due to the strong image manipulation is has been exposed to.

---

## Carousel

**URL Validation:** https://ui-patterns.com/patterns/Carousel

### Problem Summary
The user needs to browse through a set of items and possibly select one of them

### Solution
Arrange a set of items on a horizontal line where each item preferably has an thumbnail image attached (or the item is only represented by the image). Even though the list of items is long, only 3-8 images are shown at the same time.
If the user wants to view the rest of the items on the list, he or she must click one of the navigational controls such as an arrows pointing either left/right or up/down. Once one of the arrow is clicked, the subsequent “view” is loaded, a transitional animation moves the requested item into focus. The user can in this way browse the list of items back and forth in a circular fashion  hence the name Carousel.

### Rationale
A carousel optimizes screen space by displaying only a subset of images from a collection of images in a cyclic view.
The navigational controls on a carousel suggests additional content that is not currently visible, this encourages the user to continue exploring. The carousel pattern can in this way be used as an extra incentive for the user to browse through all items of the list, as we as humans do not feel comfortable by not being aware of the “full picture”.
As the carousel is circular, the start of the list will be shown after the user has reached the end. This behavior encourages the user to continue browsing through the list.

### Usage Examples
Arrange a set of items on a horizontal line where each item preferably has an thumbnail image attached (or the item is only represented by the image). Even though the list of items is long, only 3-8 images are shown at the same time.
If the user wants to view the rest of the items on the list, he or she must click one of the navigational controls such as an arrows pointing either left/right or up/down. Once one of the arrow is clicked, the subsequent “view” is loaded, a transitional animation moves the requested item into focus. The user can in this way browse the list of items back and forth in a circular fashion  hence the name Carousel.

---

## Chunking

**URL Validation:** https://ui-patterns.com/patterns/Chunking

### Problem Summary
Information grouped into familiar, manageable units is more easily processed and remembered

### Solution
Group information into a limited number of units or chunks, so that information is easier to process and recall.
Make information easier to understand and remember by breaking it down into smaller groups, or chunks. Chunking helps accommodate our limited capacity for processing information and storage in short-term memory.
Chunk larger piles of information into smaller chunks to make it easier for the user to comprehend and get an overview. Deciding on how information is chunked together can help form the users perception of what is important and worthwhile to remember.
Chunking text into paragraphs with headers allow scanning for a particular subject. The choice of headers and what should go into which paragraph help form the readers perceived meaning of the text.
How far should I chunk  and what?
Every kind of information can be chunked. You should however restrict yourself from grouping in too many chunks. There has been some discussion around what the maximum number of chunks that can be processed by short-term memory. Recent research2 suggests that the magic limit is four plus/minus one whereas older literature3 suggests up to 7 plus/minus two.
So always 4 to 5 menu items?
Do not use chunking to improve simplicity or to unclutter the design of a web page. Chunking is only to be used as an argument to ease the way we process information. Design decisions about the number of menu items, power points bullets, or radio buttons cant be justified through chunking but likely through other arguments.
When to chunk
Arguing for using the principle of chunking in design should only regard the limits on our capacity for processing information3. In other words, chunking is ideal when specific information must be memorized for later use or when an interface must compete against other stimuli for the attention of the working memory of the end user4.

	Group information into smaller chunks. Ease the cognitive load of complex tasks by grouping information into related features. By grouping items by similarity, you can far surpass the limits of storing single items. If 5 is the limit, then chunking into 5 groups f 5 dramatically expands the users capacity.
	Make scanning easier. Presenting content in chunks makes scanning easier for users and in turn improves their ability to comprehend and remember it. Create meaningful and visually distinct groups of content that make sense in the context of the larger whole. Separate headings from paragraph text.
	Auto-format inputs. Although chunking improves scannability, it can make typing more difficult. To circumvent this, consider letting input fields automatically chunk the input users are typing. Typical examples are for credit card expiration dates and phone numbers.

### Rationale
A chunk is a unit of information in short-term memory  a string of letters, a word, or a series or numbers. By chunking information into small bits we seek to accommodate the limits of our short-term memory.
The goal of chunking is to aid processing of information. Chunking helps the process by breaking longer strings of information into bit-size chunks that are easier to remember and grasp  especially when the memory is faced with competing stimuli4.

### Usage Examples
Group information into a limited number of units or chunks, so that information is easier to process and recall.
Make information easier to understand and remember by breaking it down into smaller groups, or chunks. Chunking helps accommodate our limited capacity for processing information and storage in short-term memory.
Chunk larger piles of information into smaller chunks to make it easier for the user to comprehend and get an overview. Deciding on how information is chunked together can help form the users perception of what is important and worthwhile to remember.
Chunking text into paragraphs with headers allow scanning for a particular subject. The choice of headers and what should go into which paragraph help form the readers perceived meaning of the text.
How far should I chunk  and what?
Every kind of information can be chunked. You should however restrict yourself from grouping in too many chunks. There has been some discussion around what the maximum number of chunks that can be processed by short-term memory. Recent research2 suggests that the magic limit is four plus/minus one whereas older literature3 suggests up to 7 plus/minus two.
So always 4 to 5 menu items?
Do not use chunking to improve simplicity or to unclutter the design of a web page. Chunking is only to be used as an argument to ease the way we process information. Design decisions about the number of menu items, power points bullets, or radio buttons cant be justified through chunking but likely through other arguments.
When to chunk
Arguing for using the principle of chunking in design should only regard the limits on our capacity for processing information3. In other words, chunking is ideal when specific information must be memorized for later use or when an interface must compete against other stimuli for the attention of the working memory of the end user4.

	Group information into smaller chunks. Ease the cognitive load of complex tasks by grouping information into related features. By grouping items by similarity, you can far surpass the limits of storing single items. If 5 is the limit, then chunking into 5 groups f 5 dramatically expands the users capacity.
	Make scanning easier. Presenting content in chunks makes scanning easier for users and in turn improves their ability to comprehend and remember it. Create meaningful and visually distinct groups of content that make sense in the context of the larger whole. Separate headings from paragraph text.
	Auto-format inputs. Although chunking improves scannability, it can make typing more difficult. To circumvent this, consider letting input fields automatically chunk the input users are typing. Typical examples are for credit card expiration dates and phone numbers.

---

## Collectible Achievements

**URL Validation:** https://ui-patterns.com/patterns/CollectibleAchievements

### Problem Summary
Some users respond to opportunities of winning and collecting awards that in turn can be displayed to other community members in order to increase engagement.

### Solution
Reward users for certain kinds of behavior, for reaching specifically defined goals within the community
Some users respond to opportunities of winning, earning, and collecting awards that can be displayed to other community members. Construct a consistent family of collectibles that is achieved through mastering a healthy mix of difficulties. Unlock new achievements as easier ones are accomplished.
Families of collectibles
Let your users specialize in certain types of behavior and show it off to fellow community members. If there are too many users for a single top 10 of the entire site, then create multiple top 10 lists that celebrates different specialities.
If youre running a photography website and are rewarding users for uploading great photographs, consider creating specialized awards for different types of photographs instead of just having a best-of-the-best award. It takes different sets of skills to respectively create a great portrait shot and a great action shot. So why not just reward each type?
Similarly you could award users with a series of different awards focusing on giving feedback: Best comment in this month, Highest rated reply in this month, or Elite reviewer.
It should be attractive to be rewarded
The Yahoo Design Pattern Library talks about fetishizing the awards1. Users should strive to receive a trophy, badge, or achievement  both because it is a challenge to be awarded, but also because it just looks great!
Give people something to drool over; let people know what can be won. Let them know what are available for them, what they have to unlock, and what they have achieved already.
Attractive awards work better. Develop attractive trophies with beautifully designed icons. Some games use actual game-pieces to represent each achievement.
Users should be proud to show their awards off. They should be proud to put them on display and be able to play around with their show room. If there are enough achievements to play with, you can enhance the users experience by letting him or her customize his or her show room.
Combine easy successes with hard challenges
Make some achievements very easy to accomplish, so that the user wont loose momentum. Combine these with harder challenges that require more time and effort to achieve.
In games, it is often seen that new achievements are unlocked as easier ones are accomplished. Being awarded an achievement that is not readily obtained by a newcomer adds to the users feeling of status in- and belonging to the community.
Types of achievements
There are several types of achievements to reward your users with:

	Temporal award. This type of achievement celebrates the winners of one-time events. It includes a time-frame or interval: weekly-, monthly-, or yearly awards are good examples. This kind of trophy is valid, even years after it was awarded: once earned it is never lost. An example could be Best photography 2009 or Most points in August 2009. These are useful for praising consistent top-performers and for giving a wider number of users an opportunity to earn a reputation9.
	Top 10% trophy. This trophy can be achieved just as fast as it can be lost. Whether this type of achievement belongs to a user depends on the status quo of the system. It represents the top X percent or number of community members in the moment, why users needs to maintain his or her activity in order to keep the trophy.
	Participation trophy. This kind of achievement is often used to link real-life activity with a member profile on a website. An example of such a trophy could be Participated in the 2009 Christmas party or if used for an online event: Participated in the World Photo Challenge.
	Elite acknowledgment. It gives a sense of arousal to know that you are better than somebody else. Being assigned elite status sparks motivation to further engage oneself into a community, as it does for the members still striving to achieve such status. Furthermore, elite members come out as more authoritative when they speak up, why it can be argued that they should reflect the communitys general opinion, so that they can serve as role models for newcomers.
	Privileged member acknowledgment. Certain members are so deeply involved in the community or maintenance of the site, that they are bound to be rewarded with a privileged member acknowledgment. Examples are admin, staff photographer, moderator, staff, or just VIP.
	User-to-user awards. This is not an achievement, but as they are often shown together with earned collectible achievements, they have been added to the list. These are small awards created by users (or pre-fabricated by the community) and represents gifts a user can give to another user.

What are you awarding?
What is your website about? And what object are you awarding? Are you awarding the users actions or his or her creations? Are you awarding the user or his or her objects?
At amazon.com and ebay.com, awards are used to indicate the trustworthiness of a user giving a review, selling or buying. At the Danish car-website vmax.dk, it is each car that can be awarded and not in particular the user. The owner of each car then gets to display his or her achievements for cars owned.

### Rationale
Achievements reflect a users reputation in a community. They are both a history of ones actions within that community, and a value judgment about the worth of those actions2.
Collectible achievements gives the user a feeling of ownership and belonging. It gives the user an opportunity to build an online presence that can be shown and admired by fellow community members  thus providing a sense of status in the community.
As the user collects achievements, he or she invests time in the community and builds up a history. This history with your site creates a barrier for the user to leaving, as what has been built up will be lost upon quitting. Translating the investment into visible collectible achievements helps the user to build and emotional bond the community that will reward you plentifully in traffic and loyalty.

### Usage Examples
Reward users for certain kinds of behavior, for reaching specifically defined goals within the community
Some users respond to opportunities of winning, earning, and collecting awards that can be displayed to other community members. Construct a consistent family of collectibles that is achieved through mastering a healthy mix of difficulties. Unlock new achievements as easier ones are accomplished.
Families of collectibles
Let your users specialize in certain types of behavior and show it off to fellow community members. If there are too many users for a single top 10 of the entire site, then create multiple top 10 lists that celebrates different specialities.
If youre running a photography website and are rewarding users for uploading great photographs, consider creating specialized awards for different types of photographs instead of just having a best-of-the-best award. It takes different sets of skills to respectively create a great portrait shot and a great action shot. So why not just reward each type?
Similarly you could award users with a series of different awards focusing on giving feedback: Best comment in this month, Highest rated reply in this month, or Elite reviewer.
It should be attractive to be rewarded
The Yahoo Design Pattern Library talks about fetishizing the awards1. Users should strive to receive a trophy, badge, or achievement  both because it is a challenge to be awarded, but also because it just looks great!
Give people something to drool over; let people know what can be won. Let them know what are available for them, what they have to unlock, and what they have achieved already.
Attractive awards work better. Develop attractive trophies with beautifully designed icons. Some games use actual game-pieces to represent each achievement.
Users should be proud to show their awards off. They should be proud to put them on display and be able to play around with their show room. If there are enough achievements to play with, you can enhance the users experience by letting him or her customize his or her show room.
Combine easy successes with hard challenges
Make some achievements very easy to accomplish, so that the user wont loose momentum. Combine these with harder challenges that require more time and effort to achieve.
In games, it is often seen that new achievements are unlocked as easier ones are accomplished. Being awarded an achievement that is not readily obtained by a newcomer adds to the users feeling of status in- and belonging to the community.
Types of achievements
There are several types of achievements to reward your users with:

	Temporal award. This type of achievement celebrates the winners of one-time events. It includes a time-frame or interval: weekly-, monthly-, or yearly awards are good examples. This kind of trophy is valid, even years after it was awarded: once earned it is never lost. An example could be Best photography 2009 or Most points in August 2009. These are useful for praising consistent top-performers and for giving a wider number of users an opportunity to earn a reputation9.
	Top 10% trophy. This trophy can be achieved just as fast as it can be lost. Whether this type of achievement belongs to a user depends on the status quo of the system. It represents the top X percent or number of community members in the moment, why users needs to maintain his or her activity in order to keep the trophy.
	Participation trophy. This kind of achievement is often used to link real-life activity with a member profile on a website. An example of such a trophy could be Participated in the 2009 Christmas party or if used for an online event: Participated in the World Photo Challenge.
	Elite acknowledgment. It gives a sense of arousal to know that you are better than somebody else. Being assigned elite status sparks motivation to further engage oneself into a community, as it does for the members still striving to achieve such status. Furthermore, elite members come out as more authoritative when they speak up, why it can be argued that they should reflect the communitys general opinion, so that they can serve as role models for newcomers.
	Privileged member acknowledgment. Certain members are so deeply involved in the community or maintenance of the site, that they are bound to be rewarded with a privileged member acknowledgment. Examples are admin, staff photographer, moderator, staff, or just VIP.
	User-to-user awards. This is not an achievement, but as they are often shown together with earned collectible achievements, they have been added to the list. These are small awards created by users (or pre-fabricated by the community) and represents gifts a user can give to another user.

What are you awarding?
What is your website about? And what object are you awarding? Are you awarding the users actions or his or her creations? Are you awarding the user or his or her objects?
At amazon.com and ebay.com, awards are used to indicate the trustworthiness of a user giving a review, selling or buying. At the Danish car-website vmax.dk, it is each car that can be awarded and not in particular the user. The owner of each car then gets to display his or her achievements for cars owned.

---

## Commitment  Consistency

**URL Validation:** https://ui-patterns.com/patterns/Commitment-consistency

### Problem Summary
We want to appear consistent with our stated beliefs and prior actions and also value this quality in others

### Solution
Find ways to make people state their agreement to a decision in order to pave way for similar and larger commitments in the same category, later.
Ask for small commitments or easy agreements to pave the way for bigger commitments later. To get to a more substantial agreement, make it easier for your users to buy in early and small; it will be easier for them to buy in later and larger.
Simple ways of using the Commitment and Consistency principle in web design includes:

	Add a checkbox to your form with a small action that connects to the behavior your wish to reinforce later. Adding a checkbox saying YES! I am ready for a better rate today! increased conversions by 11%1. Takeaway: Ask for a very small commitment upfront.
	Move the commitment up front. By breaking the donation process up into sequential steps, the Obama campaign increased donation conversions by 5%2, collecting millions of incremental dollars. People like to see themselves as consistent and rational – getting started with the donation amount committed them to finishing what they had started. Takeaway: Break up your “asks” into manageable steps.

Make the commitment positive and personalized. Sart your sentence with “Yes!” and personalize the headline  for example “Yes – I am ready to improve my website’s conversion rate!”
Getting commitments to work

	Find relevant ways. Look for positive, relevant ways to encourage people to make public, active, and voluntary commitments  and build on those.
	Small commitments pave the way. Ask for small commitments or easy agreements, to pave the way for even bigger commitments. To get to a more substantial agreement, make it easier for your users to buy in early and small. And it will be easier for them to buy in later and larger.
	Build momentum. Look for opportunities achieve small wins that demonstrate progress  and the direction of your larger persuasive objective.

Getting it Right
With the goal of not manipulating, but rather, fostering genuine, positive actions that benefit both individuals and organizations, these are effective implementation strategies:

	Start Small. Utilizing the Foot-in-the-Door technique, begin with a minor request that a person is likely to agree to. This can pave the way for larger, related requests. For example, asking users to sign up for a newsletter can increase the likelihood of them making a purchase later.
	Public Commitments. When people make commitments publicly, theyre more likely to follow through. This is because public declarations not only influence the individuals self-perception but also create a sense of accountability to others.
	Writing it Down. Theres power in the written word. When individuals write down their commitments or beliefs, it reinforces their attachment to them. This is why testimonials or setting written goals can be so influential.
	Positive and Personalized Commitments. Frame commitments in a positive light and personalize the request. Starting a commitment with affirmations like Yes! or personalizing the commitment to the individual can make it more compelling.
	Not all commitments are equal. Just because someone agrees to a minor request doesnt guarantee theyll agree to a larger, related one.
	Sequential steps. Breaking processes into manageable steps can increase user engagement and completion rates.
	Affirmative actions. Incorporate checkboxes or options that affirm a users commitment. This can be as simple as a checkbox saying, Yes, I want to stay updated!

### Rationale
People like to be consistent with the things they have previously said or done. People generally want to be seen, as honoring their commitments consistently; as somebody who can be counted on, instead of somebody who flip flops, and is without self-control.
Once we have publicly said out loud, that we use or like a product or that we are going to start doing something, we have a desire to act in a manner consistent with that behavior. If I state that I am going to start running 3 times a week, I have a desire to act consistently with that statement.
People have an innate desire to be consistent with their words and actions. This desire is so strong that individuals will sometimes go to great lengths to maintain consistency, even when doing so may not be in their best interests.
Why is this so?

	Cultural value. Consistency is often valued in societies. Inconsistent individuals can be viewed as unreliable or deceitful.
	Self-perception. Once we commit to something publicly, we tend to act in ways that are congruent with that commitment. This aligns with our self-image and how we want others to perceive us.
	Cognitive ease. Being consistent reduces the cognitive load. Its simpler to continue in a set pattern than to evaluate every decision afresh.

### Usage Examples
Find ways to make people state their agreement to a decision in order to pave way for similar and larger commitments in the same category, later.
Ask for small commitments or easy agreements to pave the way for bigger commitments later. To get to a more substantial agreement, make it easier for your users to buy in early and small; it will be easier for them to buy in later and larger.
Simple ways of using the Commitment and Consistency principle in web design includes:

	Add a checkbox to your form with a small action that connects to the behavior your wish to reinforce later. Adding a checkbox saying YES! I am ready for a better rate today! increased conversions by 11%1. Takeaway: Ask for a very small commitment upfront.
	Move the commitment up front. By breaking the donation process up into sequential steps, the Obama campaign increased donation conversions by 5%2, collecting millions of incremental dollars. People like to see themselves as consistent and rational – getting started with the donation amount committed them to finishing what they had started. Takeaway: Break up your “asks” into manageable steps.

Make the commitment positive and personalized. Sart your sentence with “Yes!” and personalize the headline  for example “Yes – I am ready to improve my website’s conversion rate!”
Getting commitments to work

	Find relevant ways. Look for positive, relevant ways to encourage people to make public, active, and voluntary commitments  and build on those.
	Small commitments pave the way. Ask for small commitments or easy agreements, to pave the way for even bigger commitments. To get to a more substantial agreement, make it easier for your users to buy in early and small. And it will be easier for them to buy in later and larger.
	Build momentum. Look for opportunities achieve small wins that demonstrate progress  and the direction of your larger persuasive objective.

Getting it Right
With the goal of not manipulating, but rather, fostering genuine, positive actions that benefit both individuals and organizations, these are effective implementation strategies:

	Start Small. Utilizing the Foot-in-the-Door technique, begin with a minor request that a person is likely to agree to. This can pave the way for larger, related requests. For example, asking users to sign up for a newsletter can increase the likelihood of them making a purchase later.
	Public Commitments. When people make commitments publicly, theyre more likely to follow through. This is because public declarations not only influence the individuals self-perception but also create a sense of accountability to others.
	Writing it Down. Theres power in the written word. When individuals write down their commitments or beliefs, it reinforces their attachment to them. This is why testimonials or setting written goals can be so influential.
	Positive and Personalized Commitments. Frame commitments in a positive light and personalize the request. Starting a commitment with affirmations like Yes! or personalizing the commitment to the individual can make it more compelling.
	Not all commitments are equal. Just because someone agrees to a minor request doesnt guarantee theyll agree to a larger, related one.
	Sequential steps. Breaking processes into manageable steps can increase user engagement and completion rates.
	Affirmative actions. Incorporate checkboxes or options that affirm a users commitment. This can be as simple as a checkbox saying, Yes, I want to stay updated!

---

## Competition

**URL Validation:** https://ui-patterns.com/patterns/Competition

### Problem Summary
When sharing the same environment, well strive to attain things that cannot be shared

### Solution
Leverage our natural drive to compete to motivate users to adopt a target attitude or behavior. Competiition energizes and prompts participants to invest time and effort as they care about the outcome. In many situations, no extrinsic motivator (reward) is need to motivated as the competition in itself is both energizing and motivating.

	Boost engagement. Being in a competition, its participants focus on their outcome will match competitors. This in turn boosts their engagement and activity.
	Incentivise self-improvement. Competition remains a great mechanism to provide incentives for self-improvement as achieving the best outcome often requires introspection.
	Mind the group. If used among individuals, be careful about recognizing one person at the expense of the group.

### Rationale
Competition is a great mechanism to provide incentives for self-improvement. Consider what people might be competing for within your system: attention or resources? Competition can be among individuals or groups, and goals can be opposing, shared, or even complementary.
Competition motivates engagement in two ways: internally, by utilising our urge to understand and think, and externally by utilizing our need for social status.

### Usage Examples
Leverage our natural drive to compete to motivate users to adopt a target attitude or behavior. Competiition energizes and prompts participants to invest time and effort as they care about the outcome. In many situations, no extrinsic motivator (reward) is need to motivated as the competition in itself is both energizing and motivating.

	Boost engagement. Being in a competition, its participants focus on their outcome will match competitors. This in turn boosts their engagement and activity.
	Incentivise self-improvement. Competition remains a great mechanism to provide incentives for self-improvement as achieving the best outcome often requires introspection.
	Mind the group. If used among individuals, be careful about recognizing one person at the expense of the group.

---

## Completeness meter

**URL Validation:** https://ui-patterns.com/patterns/CompletenessMeter

### Problem Summary
The user wants to complete a goal but needs guidance in when it is reached and how to reach it.

### Solution
Let users gauge progress toward reaching an end goal. Divide the end goal into smaller sub-tasks, and increase the percentage of completeness as each task is completed.
Divide and end-goal into several sub-tasks. The end-goal can be arbitrarily defined, such as Completeness of your profile or Elite member. As each sub-task is completed, the percentage of completed tasks goes up  reaching 100% when the goal is finished.
It is often seen that along with stating the progress of the goal (for instance: 34% done), one or more links or hints to how the progress can be improved is also provided. This will help keep the user on track and immediately move to the next task once one has been completed.
There are several approaches to presenting and celebrating an end-goal state. One option is simply to indicate that all tasks have been completed (as in “Your profile is complete!”) along with a “100%” mark. Another is to award the user with a collectible achievement: a badge, trophy, or similar award that he or she can decorate his personal profile with and show off to his or her friends.
A third way to celebrate completing the goal and its sub-tasks is to announce it in his or her profile feed, or even on a centralized site-wide feed.

### Rationale
Extrinsically motivate users by triggering their desire for achievement, curiosity, and completion by providing a feedback loop that lets users gauge their progress toward reaching an end goal.
This pattern uses a set of psychological drivers that pushes the user to move forward towards the end goal.
One is curiosity. We are curious to find out what happens when we reach 100%. Will I be rewarded or will my profile look different?
Another is the feedback loop. As the user completes sub-tasks, his or her progress moves towards 100%. A clear link between completing tasks and reaching the end goal has been established.

### Usage Examples
Let users gauge progress toward reaching an end goal. Divide the end goal into smaller sub-tasks, and increase the percentage of completeness as each task is completed.
Divide and end-goal into several sub-tasks. The end-goal can be arbitrarily defined, such as Completeness of your profile or Elite member. As each sub-task is completed, the percentage of completed tasks goes up  reaching 100% when the goal is finished.
It is often seen that along with stating the progress of the goal (for instance: 34% done), one or more links or hints to how the progress can be improved is also provided. This will help keep the user on track and immediately move to the next task once one has been completed.
There are several approaches to presenting and celebrating an end-goal state. One option is simply to indicate that all tasks have been completed (as in “Your profile is complete!”) along with a “100%” mark. Another is to award the user with a collectible achievement: a badge, trophy, or similar award that he or she can decorate his personal profile with and show off to his or her friends.
A third way to celebrate completing the goal and its sub-tasks is to announce it in his or her profile feed, or even on a centralized site-wide feed.

---

## Goal-Gradient Effect

**URL Validation:** https://ui-patterns.com/patterns/Completion

### Problem Summary
Our motivation increases as we move closer to a goal

### Solution
Provide a feeling of closure by rewarding users at the completion of a goal
If your application is geared toward a purpose with an end goal, you can use the fact the our Need for closure drive us toward a well defined end-goal.
Optionally, you can divide a larger task into fewer sub-tasks and use the completion of each sub-task to give the user a break and/or communicate what is next.
Set and communicate expectations and progress.
They key is to set expectations and communicate progress in order to utilize the motivational powers of this reward. Expectations can be set and communicated in multiple dimensions:

	In time, how long is the process
	In resources, how much effort is to be put into the process of reaching completion. How many man hours, money, etc. is to be put into reaching the end-goal.
	In quality, what are the requirements of completing sub-tasks or entirely completing a process.
	In progress, how much of the whole process has already been completed. How many resources, how much time, and in what quality can I expect to deliver in order to reach completion?

Making the completion official
If completing the end-goal of the application entitles to bragging rights, provide a way for users to communicate their completion. Common ways to communicate completion are:

	Badges, trophies, and achievements  as when unlocking a Super Swarm Badge on Foursquare or achieving the Booster badge on stackoverflow.com.
	Certification  as when you complete a course and become a certified engineer.
	Diploma  as when you complete an education an reach a degree.

Provide artificial progress
A 10-space coffee card pre-stamped twice will be completed faster than an 8 with no pre-stamps. Providing artificial progress towards a goal will help to ensure users are more likely to complete a task or purchase.
Beware of the post-reward reset effect
Our motivation has a tendency to drop immediately after after a goal has been reached  even when there is a second reward in the horizon. Consider how you can counterbalance this phenomenon.
Divide larger tasks into sub-tasks
And reward users for completion of each

### Rationale
Far-away rewards are much less motivating than near term ones. If you are offering rewards for specific user actions, you will most likely want to reward sooner than later. By increasing the velocity of rewards, you may find that the total reward sum needed will be lower.
Furthermore, the illusion of progress toward a goal induces task and purchase acceleration.

### Usage Examples
Provide a feeling of closure by rewarding users at the completion of a goal
If your application is geared toward a purpose with an end goal, you can use the fact the our Need for closure drive us toward a well defined end-goal.
Optionally, you can divide a larger task into fewer sub-tasks and use the completion of each sub-task to give the user a break and/or communicate what is next.
Set and communicate expectations and progress.
They key is to set expectations and communicate progress in order to utilize the motivational powers of this reward. Expectations can be set and communicated in multiple dimensions:

	In time, how long is the process
	In resources, how much effort is to be put into the process of reaching completion. How many man hours, money, etc. is to be put into reaching the end-goal.
	In quality, what are the requirements of completing sub-tasks or entirely completing a process.
	In progress, how much of the whole process has already been completed. How many resources, how much time, and in what quality can I expect to deliver in order to reach completion?

Making the completion official
If completing the end-goal of the application entitles to bragging rights, provide a way for users to communicate their completion. Common ways to communicate completion are:

	Badges, trophies, and achievements  as when unlocking a Super Swarm Badge on Foursquare or achieving the Booster badge on stackoverflow.com.
	Certification  as when you complete a course and become a certified engineer.
	Diploma  as when you complete an education an reach a degree.

Provide artificial progress
A 10-space coffee card pre-stamped twice will be completed faster than an 8 with no pre-stamps. Providing artificial progress towards a goal will help to ensure users are more likely to complete a task or purchase.
Beware of the post-reward reset effect
Our motivation has a tendency to drop immediately after after a goal has been reached  even when there is a second reward in the horizon. Consider how you can counterbalance this phenomenon.
Divide larger tasks into sub-tasks
And reward users for completion of each

---

## Conceptual Metaphor

**URL Validation:** https://ui-patterns.com/patterns/Conceptual-metaphor

### Problem Summary
We understand a new idea or concept by linking it to another

### Solution
Explain difficult concepts by making analogies.

	Draw favorable analogies. Help users understand a concept and influence how it iis perceived by drawing a literal or implied analogy.
	Make the unfamiliar familiar. Using conceptual metaphors to explain unfamiliar concepts with familiar ones, eases understanding something that might otherwise be too complex or too abstract for our mind to grasp.
	Make the abstract concrete. Conceptual metaphors make abstract concepts more concrete and therefore bring them within our reach. Draw visual, functional, and structural similarities to make the point.
	Make the obvious emotional. Link your product with a familiar concept to transfer its emotions to your product.

### Rationale
Letting users grasp an idea by association can help ease understanding, influence how it is perceived, and adjust how we think and act.
Explain difficult concepts by making analogies. Letting users grasp an idea by association can help ease understanding, influence how it is perceived, and adjust how we think and act. Although time and culture sensitive, conceptual metaphors have the power to create a sense of familiarity, trigger emotions, draw attention, and motivate action.

### Usage Examples
Explain difficult concepts by making analogies.

	Draw favorable analogies. Help users understand a concept and influence how it iis perceived by drawing a literal or implied analogy.
	Make the unfamiliar familiar. Using conceptual metaphors to explain unfamiliar concepts with familiar ones, eases understanding something that might otherwise be too complex or too abstract for our mind to grasp.
	Make the abstract concrete. Conceptual metaphors make abstract concepts more concrete and therefore bring them within our reach. Draw visual, functional, and structural similarities to make the point.
	Make the obvious emotional. Link your product with a familiar concept to transfer its emotions to your product.

---

## Continuous Scrolling

**URL Validation:** https://ui-patterns.com/patterns/ContinuousScrolling

### Problem Summary
The user needs to view a subset of data that is not easily displayed on a single page



Content needs to be presented to users as a subset of a much larger seemingly endless set, in a way that will aid them in consuming content without effort.

### Solution
Automatically load the next set or page of content as the user reaches the bottom of the current page
In contrast to the Pagination patterns, the Continuous Scrolling pattern has no natural break. When using pagination patterns, a decision to only show a subset of data at a time and then let the user request more data if wanted is chosen. With the Continuous Scrolling, new data is automatically retrieved as the user has scrolled to the bottom of the page. It thus appears as if the page has no end, as more data will be loaded and inserted into the page each time the user scrolls to the bottom of page.

### Rationale
Eliminate the need for clicking next page by creating the effect of an infinitely scrolling page by constantly loading in new content as the user scrolls to the bottom of a page. Though great for the user experience, this pattern introduces bookmarking issues.
The problem with using pagination for browsing between subsets of data is that the user is pulled from the world of content to the world of navigation, as the user is required to click to the next page. The user is then no longer thinking about what they are reading, but about how to get more to read. This breaks the users train of thought and forces them to stop reading. Using pagination creates a natural pause that lets the user reevaluate if he or she wants to keep going on or leave the site, which they a lot of the time do.
It can be argued that Continuous Scrolling can be frustrating for the user, as there is no natural pause. The user will ask himself: When am I done reading?

### Usage Examples
Automatically load the next set or page of content as the user reaches the bottom of the current page
In contrast to the Pagination patterns, the Continuous Scrolling pattern has no natural break. When using pagination patterns, a decision to only show a subset of data at a time and then let the user request more data if wanted is chosen. With the Continuous Scrolling, new data is automatically retrieved as the user has scrolled to the bottom of the page. It thus appears as if the page has no end, as more data will be loaded and inserted into the page each time the user scrolls to the bottom of page.

---

## Copy Box

**URL Validation:** https://ui-patterns.com/patterns/CopyBox

### Problem Summary
Users need to easily view and copy preformatted text.

### Solution
Create a box that has its own style in regards font color, font style, and background color that distinguishes itself from the rest of the page.
To preserve indentation and general formatting of the text box so that it looks like a terminal window or text editor, use a mono-space font: a font that has a fixed width typeface (glyphs have the same width).
As inserting text in raw HTML renders without line breaks and strips repeating spaces, you need to put special tags around the text you want to preserve the original formatting with. One solution is to use the pre around the text you want to preserve formatting with  another is to put the text inside a textarea.

### Rationale
If you just paste ascii formatted text into a HTML file, the users browser will format the text and display it all in one line and regardless of how the code looks like in the HTML file as special tags are used in HTML to define line breaks (br).

### Usage Examples
Create a box that has its own style in regards font color, font style, and background color that distinguishes itself from the rest of the page.
To preserve indentation and general formatting of the text box so that it looks like a terminal window or text editor, use a mono-space font: a font that has a fixed width typeface (glyphs have the same width).
As inserting text in raw HTML renders without line breaks and strips repeating spaces, you need to put special tags around the text you want to preserve the original formatting with. One solution is to use the pre around the text you want to preserve formatting with  another is to put the text inside a textarea.

---

## Coupon

**URL Validation:** https://ui-patterns.com/patterns/Coupon

### Problem Summary
You want to attract users to purchase products using an incentive.

### Solution
Create a field specifically for entering a coupon / promotional code. Entering a code gives the customer a certain amount of discount depending on what code has been entered. On the merchants side, a number of different codes can be constructed in order to 1) measure where your customers come from and have heard of you and 2) allow different discount rates for different groups.
Types of coupon offers
Coupons give access to a variety of discounts and offers. The most common are:

	Percentage Based Discount: The most common coupon type is the one giving access to percentage based discounts.
	Dollar Value Discount: Coupon offers based on the dollar value of a product makes people feel like theyre wasting money if they don’t use it. In some studies, redemption of dollar based offers vs. percentage based offers can be as much as 175% greater1.
	Free Shipping: Coupons that give access to free shipping is often provided in confunction with a minimum order size to help increase the average order value.
	Free Gift: Coupons providing a free gift to your order require customers to purchase at least one other item and often of a minimum value

### Rationale
Using coupons codes to attract customers to buy a merchants product builds on the customers assumption that the offer is short lived, why action must be taken soon in order not to loose the psychological gain created by receiving the coupon code. As losses are mentally valued with greater weight than gains, the customer will be aversive towards losing the gain given and act on it while time is. Check out the Value Function as proposed by Tversky and Kahneman, 1991: Loss Aversion in Riskless Choice.
Another benefit of Coupon codes its traceability. Marketeers can branch out different codes to find out which campaign generated the most leads.

### Usage Examples
Create a field specifically for entering a coupon / promotional code. Entering a code gives the customer a certain amount of discount depending on what code has been entered. On the merchants side, a number of different codes can be constructed in order to 1) measure where your customers come from and have heard of you and 2) allow different discount rates for different groups.
Types of coupon offers
Coupons give access to a variety of discounts and offers. The most common are:

	Percentage Based Discount: The most common coupon type is the one giving access to percentage based discounts.
	Dollar Value Discount: Coupon offers based on the dollar value of a product makes people feel like theyre wasting money if they don’t use it. In some studies, redemption of dollar based offers vs. percentage based offers can be as much as 175% greater1.
	Free Shipping: Coupons that give access to free shipping is often provided in confunction with a minimum order size to help increase the average order value.
	Free Gift: Coupons providing a free gift to your order require customers to purchase at least one other item and often of a minimum value

---

## Endowment Effect

**URL Validation:** https://ui-patterns.com/patterns/Endowment-effect

### Problem Summary
We place greater value on objects we own over objects we do not, especially if sentimental value has been placed in them

### Solution
The endowment effect can be described as the divergence between willingness to buy and willingness to sell. We place higher value on objects we own over objects we do not, especially if sentimental value has been placed in them. Ownership creates satisfaction.

### Rationale
When we get something, we adjust to our level of ownership, which then becomes the baseline by which we judge future gains and losses. Possession feels like ownership: consider giving away free trials or make users invest time in your service.
In a university study, students were parted into two equally sized groups. One group was given mugs (seller) and the other (chooser) nothing. When asked, the sellers in average wanted $7.00 for the mug, whereas the choosers were only willing to pay $3.50. The mug was evaluated as a gain by the choosers and as a loss by the sellers.
As users sign up, start build their account, and making it theirs, the endowment effect comes into play. Amazon does it well by letting its users make wish lists, make gift organizers, rate and recommend products, make lists, award users with â€œ#1 reviewerâ€ badges, and more. As users interact with Amazon and gain ownership over the Amazon website, the endowment effect makes them place higher value on conducting transactions on amazon.com vs barnesandnoble.com.
Another successful website to use the endowment effect to retain users is the online radio station: last.fm. When users listen to music at last.fm, they can choose to love what they hear and thereby indicate to last.fm that they are interested in hearing something similar again. Last.fm remembers what music you love and constructs a metric of your music taste that it uses to deliver music that caters to your preference. The website has managed to let the user take ownership in the site with the music profile build up with consistent use. The has resulted in many preferring to listen to music over the Internet via last.fm than over their iPod or through the CD collection.

### Usage Examples
The endowment effect can be described as the divergence between willingness to buy and willingness to sell. We place higher value on objects we own over objects we do not, especially if sentimental value has been placed in them. Ownership creates satisfaction.

---

## Event Calendar

**URL Validation:** https://ui-patterns.com/patterns/EventCalendar

### Problem Summary
The user wants to find events of interest happening in a certain period of time.



Events need to be presented to users in a visually concise model that abstracts date and time.

### Solution
Separate content into meaningful buckets of time. Organize events into groups of tonight, next week, next month, or merely September or October. Show more details for an event as it nears today and focus on scannability and filtering the further away it is.
The most common ways to browse an event calendar is either through a text list of events, through a month table, or a combination of both.
The text list is great for providing a view of events for a given period of time: for a certain day, week, month, or simply the nearest future. With a packed calendar, it can however be overwhelming to get and overview of everything.
The calendar box (month table) is good for browsing between days and for getting an overview of when the action happens. In isolation it however reveals close to no information about the events in the calendar. Furthermore, the boxed calendar renders almost useless without data. If you only have one or two events a month, the usefulness of the calendar box becomes minimal  left to merely showing when the next weekend is up.
When combined, the calendar box can be used as a device for navigating through periods of time, while text lists can show details. Again, the boxed month calendar renders useless if you only have 2 events a month, where you might be better off with a mere list of years or no time navigation.
The elements of an event list
For an event calendar to work, you must provide a range of different types of information for it to be useful. It all depends on the context. If you are listing concert events then ticket prices, availability of tickets, and band name a important. For a conference calendar, the presenter, room name, conference track name, and duration of the talk might be important.
Regardless of the context, there seems to be some details that are always important:

	Title of the event
	Date of the event
	Start time
	Location
	Organizer
	Description of the event

### Rationale
An event calendar is a list of time-based items. Their base in time is a great tool for grouping, filtering, and sorting.

### Usage Examples
Separate content into meaningful buckets of time. Organize events into groups of tonight, next week, next month, or merely September or October. Show more details for an event as it nears today and focus on scannability and filtering the further away it is.
The most common ways to browse an event calendar is either through a text list of events, through a month table, or a combination of both.
The text list is great for providing a view of events for a given period of time: for a certain day, week, month, or simply the nearest future. With a packed calendar, it can however be overwhelming to get and overview of everything.
The calendar box (month table) is good for browsing between days and for getting an overview of when the action happens. In isolation it however reveals close to no information about the events in the calendar. Furthermore, the boxed calendar renders almost useless without data. If you only have one or two events a month, the usefulness of the calendar box becomes minimal  left to merely showing when the next weekend is up.
When combined, the calendar box can be used as a device for navigating through periods of time, while text lists can show details. Again, the boxed month calendar renders useless if you only have 2 events a month, where you might be better off with a mere list of years or no time navigation.
The elements of an event list
For an event calendar to work, you must provide a range of different types of information for it to be useful. It all depends on the context. If you are listing concert events then ticket prices, availability of tickets, and band name a important. For a conference calendar, the presenter, room name, conference track name, and duration of the talk might be important.
Regardless of the context, there seems to be some details that are always important:

	Title of the event
	Date of the event
	Start time
	Location
	Organizer
	Description of the event

---

## Fat Footer

**URL Validation:** https://ui-patterns.com/patterns/FatFooter

### Problem Summary
Users need a mechanism that will enable them to quickly access specific sections of a site or application bypassing the navigational structure.

### Solution
End a page by providing relevant links to other sections of your site.
Add the same footer on all pages of a website  with the same layout in the footer on all pages. Typically, these things are included in fat footer designs:

	About us link: Link to your about us section, which then includes basic information about your company.
	Terms of service: If you provide a service or a product, placing a link to it in the footer is a standard location, why users anticipate it being there.
	Privacy policy: As with the terms of service, users expect to always be able to find privacy policies in the footer of a website.
	Site map: Provide quick links the most important pages of your website.
	Contact us link: Make sure your users have a way to get in hold of you. If you have a Contact us page, users expect to find a link to it in the footer. This is also a critical point in building the trustworthiness of your site as it is displaying your physical address.
	Address and phone number: Show that you are real. If you have a physical business, offer phone support, or have a reason for people to mail you things, putting that information in the footer is an anticipated and appropriate location.
	Social links: Link to any social presences you might have on Facebook, Twitter, Pinterest, Instagram, and the likes.

### Rationale
Keep visitors on your site for longer: end one experience by starting a new one. Provide easy and natural ways for users to continue their journey. By adding a shortcut to the most frequently used pages and functions, the path can be shortened and confusion can be decreased.
The hierarchical structure of a website can at times impede the path to specific page or function of a website. By adding a shortcut to the most frequently used pages and functions, the path can be shortened: the number of clicks can be lessened and the confusion decreased.

### Usage Examples
End a page by providing relevant links to other sections of your site.
Add the same footer on all pages of a website  with the same layout in the footer on all pages. Typically, these things are included in fat footer designs:

	About us link: Link to your about us section, which then includes basic information about your company.
	Terms of service: If you provide a service or a product, placing a link to it in the footer is a standard location, why users anticipate it being there.
	Privacy policy: As with the terms of service, users expect to always be able to find privacy policies in the footer of a website.
	Site map: Provide quick links the most important pages of your website.
	Contact us link: Make sure your users have a way to get in hold of you. If you have a Contact us page, users expect to find a link to it in the footer. This is also a critical point in building the trustworthiness of your site as it is displaying your physical address.
	Address and phone number: Show that you are real. If you have a physical business, offer phone support, or have a reason for people to mail you things, putting that information in the footer is an anticipated and appropriate location.
	Social links: Link to any social presences you might have on Facebook, Twitter, Pinterest, Instagram, and the likes.

---

## Feedback Loops

**URL Validation:** https://ui-patterns.com/patterns/Feedback-loops

### Problem Summary
We are influenced by information that provides clarity on our actions

### Solution
Allow people to play interactively with information so they can adjust their behavior and future actions toward reaching a greater goal. Use numeric data to show progress and translate data into analogous visual information.
Provide measures toward letting users know how what they are doing is affecting the system. This in turn allows users to adjust their behavior and future actions toward reaching a greater goal.

### Rationale
Every action creates an equal opposite reaction. When reactions loop back to affect themselves, a feedback loop is created1.

### Usage Examples
Allow people to play interactively with information so they can adjust their behavior and future actions toward reaching a greater goal. Use numeric data to show progress and translate data into analogous visual information.
Provide measures toward letting users know how what they are doing is affecting the system. This in turn allows users to adjust their behavior and future actions toward reaching a greater goal.

---

## Fill in the Blanks

**URL Validation:** https://ui-patterns.com/patterns/FillInTheBlanks

### Problem Summary
The user needs to enter data into the system

### Solution
Order input fields in the form of a sentence with input fields as blank spaces to be filled by the user. Write a sentence and let the user fill in the blanks of the sentence by selecting or filling out input fields that are in place of words.
When the input field is not inserted at the end or the beginning of the sentence, it is important for the general readability and understandability of the interface, that the input fields does not take up more space than the height of one text-line. Input text boxes, and drop-down lists therefore work the best for this sort of usage.
The pattern is often seen in applications that filter large lists out by conditions. In Apples iTunes, the pattern is used to create conditions for smart playlists (See examples at bottom of page).
The biggest drawback of the pattern is its poor ability to be localized into different languages as the placement of each input will possibly have to be rearranged to match the grammar of each language. Using Fill in the blanks in this way hinders immediate conversion of a user interface to other languages.

### Rationale
We all know how to finish a sentence. By inserting input fields into a sentence of words, the user interface is made self-explanatory, possible misundestandings are minimized, and the context is understood more clearly.
Sometimes, it can be hard to find a describing label for an input that does not alienate the user to the system.
Consider the example in the bottom of the page from the Ruby On Rails wiki. Here, both the submit button (Save), the input field for the author name, as well as a back in history link are presented all in the same sentence. These three options could have easily been represented on separate lines with a separate label for each option. Instead, the three options are presented as a sentence, and thus put in context of each other.
Furthermore, the example above uses the Input Prompt pattern to encourage users to fill out the text field.
The Fill in the blanks makes the interface somewhat self-explanatory. Our semantic capabilities as human beings allow us to fill in the missing parts of a sentence.

### Usage Examples
Order input fields in the form of a sentence with input fields as blank spaces to be filled by the user. Write a sentence and let the user fill in the blanks of the sentence by selecting or filling out input fields that are in place of words.
When the input field is not inserted at the end or the beginning of the sentence, it is important for the general readability and understandability of the interface, that the input fields does not take up more space than the height of one text-line. Input text boxes, and drop-down lists therefore work the best for this sort of usage.
The pattern is often seen in applications that filter large lists out by conditions. In Apples iTunes, the pattern is used to create conditions for smart playlists (See examples at bottom of page).
The biggest drawback of the pattern is its poor ability to be localized into different languages as the placement of each input will possibly have to be rearranged to match the grammar of each language. Using Fill in the blanks in this way hinders immediate conversion of a user interface to other languages.

---

## Fixed rewards

**URL Validation:** https://ui-patterns.com/patterns/Fixed-rewards

### Problem Summary
Use rewards to encourage continuation or introduction of wanted behavior

### Solution
Rewards is a mechanism for telling users that they have done well  that their actions have been judged favorably.
Fixed rewards
Fixed rewards are given out at a set time, amount, and type and are opposed to variable rewards, which feel more like random rewards.
In computer games, fixed rewards are given out when you complete a level or achieve some other kind of clearly defined goal. Variable rewards are usually given out when killing monsters.
In web applications fixed rewards are the most commonly used type of reward as they provide clear goals for users to strive for. At Hacker News, features such as voting on comments, or changing template colors are unlocked as you collect Karma points for your activities. At Stackoverflow.com, you receive a badge as you engage more and more in the community. Both provide clear set goals that users can strive for in order to climb up the ladder of status in the community.
The right reward at the right time and amount
Everyone likes to be told they are doing a good job, but it is essential for rewards to work that they are given out at the right time, in the right amount, and that it is the right rewards that is being given. Ask these questions for each opportune moment to determine what is right1:

	What rewards is the system giving at the moment? Can it give out others as well?
	Are users excited when they get rewards or bored by them? Why is this?
	Do users understand the rewards they are given? Getting a reward you dont understand is like getting no reward at all.
	Are rewards given out on a too regular schedule? Can they be given out in a more variable way ?
	How are rewards related to one another? Is there a way that they can be connected?
	How are the rewards of the system building? Too fast? Too slow? Or just right?

There is only one way to find out the right balance of time, amount, and kind of reward: through trial and error. Balancing rewards is often a question of good enough1.
Types of rewards
There are several types of rewards that games and web applications can give. These are the most common1.

	Praise
	Points
	Prolonged play
	A gateway  or unlocking features
	Expression
	Powers
	Completion

### Rationale
Use rewards to encourage continuation or introduction of wanted behavior in your users.

### Usage Examples
Rewards is a mechanism for telling users that they have done well  that their actions have been judged favorably.
Fixed rewards
Fixed rewards are given out at a set time, amount, and type and are opposed to variable rewards, which feel more like random rewards.
In computer games, fixed rewards are given out when you complete a level or achieve some other kind of clearly defined goal. Variable rewards are usually given out when killing monsters.
In web applications fixed rewards are the most commonly used type of reward as they provide clear goals for users to strive for. At Hacker News, features such as voting on comments, or changing template colors are unlocked as you collect Karma points for your activities. At Stackoverflow.com, you receive a badge as you engage more and more in the community. Both provide clear set goals that users can strive for in order to climb up the ladder of status in the community.
The right reward at the right time and amount
Everyone likes to be told they are doing a good job, but it is essential for rewards to work that they are given out at the right time, in the right amount, and that it is the right rewards that is being given. Ask these questions for each opportune moment to determine what is right1:

	What rewards is the system giving at the moment? Can it give out others as well?
	Are users excited when they get rewards or bored by them? Why is this?
	Do users understand the rewards they are given? Getting a reward you dont understand is like getting no reward at all.
	Are rewards given out on a too regular schedule? Can they be given out in a more variable way ?
	How are rewards related to one another? Is there a way that they can be connected?
	How are the rewards of the system building? Too fast? Too slow? Or just right?

There is only one way to find out the right balance of time, amount, and kind of reward: through trial and error. Balancing rewards is often a question of good enough1.
Types of rewards
There are several types of rewards that games and web applications can give. These are the most common1.

	Praise
	Points
	Prolonged play
	A gateway  or unlocking features
	Expression
	Powers
	Completion

---

## Forgiving Format

**URL Validation:** https://ui-patterns.com/patterns/ForgivingFormat

### Problem Summary
The user needs to quickly enter data into the system, which then in turn interprets the users input.

### Solution
Allow users to enter text in their own format and syntax, and let the system interpret it intelligently
Let users focus on getting things done rather than typing in things correctly. Lower the barrier for users to interact by allowing a broad spectrum of formats and syntaxes to be inputted. Consider nudging users to provide more easily interpreted information by paying attention to how you ask for input.
Transfer the problem inputting data from a user interface problem to a programming problem. Behind the scenes, an interpreter checks for different word patterns, and converts them into a formatted value.

### Rationale
Using the forgiving format pattern saves space and decreases the barrier for the user to interact with the system.
Depending on how widely defined the input topic is, it can be increasingly hard for the backend program to interpret the input field. The success of this pattern has much to do with how information requested – how the user is prompted.

### Usage Examples
Allow users to enter text in their own format and syntax, and let the system interpret it intelligently
Let users focus on getting things done rather than typing in things correctly. Lower the barrier for users to interact by allowing a broad spectrum of formats and syntaxes to be inputted. Consider nudging users to provide more easily interpreted information by paying attention to how you ask for input.
Transfer the problem inputting data from a user interface problem to a programming problem. Behind the scenes, an interpreter checks for different word patterns, and converts them into a formatted value.

---

## Gallery

**URL Validation:** https://ui-patterns.com/patterns/Gallery

### Problem Summary
The user needs to browse a collection of high quality images

### Solution
A gallery consists of multiple images that can be browsed one by one by navigating between them. Only one image is viewed at a time. Often, several different options for navigating the gallery is provided in order to accommodate  several different browsing behaviors of the different kinds of users browsing the gallery. It is common for a gallery to display the context the current image image being views as in Image 2 out of 18 images, the shorter 2 out of 18, or merely 2/18.
Navigation options often include

	Previous and next image buttons
	A series of thumbnail images arranged in one of the following ways:
	
		Previous- and next images with links to these images
		The 2 or 3 of the nearest images (previous 2 or 3 and next 2 or 3 images) with links to these images
		A list of all images in the gallery arranged in a grid  often with 3, 4, or 5 images in each row.
	
	A text link after the image caption text saying Next image, Next, or the title of the next image.
	Tabs with image numbers linking to each image in the gallery.
	Clicking the current image itself tend to yield one of two effects: (1) Zoom the image or (2) navigate to the next image
	Keyboard arrow key listeners: left arrow fires a show previous image event, right arrow fires a show next image event.

Tips for designing a gallery
Provide thumbnails and numbers
Thumbnails allow the user to find out where he or she is in the gallery: the context of the current image. Thumbnails also provide a great way to keep the user in the flow of going to the next image; if the image seems interesting in thumbnail mode it might be worth a click from the users perspective.
Listing the gallery images as numbers allows for quick navigation. Highlight the current image to let the user know where he or she is in the gallery: the context of the current image.
Decide on auto (slideshow) or manual (or both)
Galleries (or slideshows) work in one of two ways: either they switch automatically from image to image after a set time interval, or buttons and other navigation elements are provided to let the user browse through images manually. Some galleries provide pause buttons and thus provides a mix between the two.
Reload the entire page or change only the important parts
Newer galleries tend to be based on javascript where only the image, its context, captions, and comments are changed as opposed to having a complete page reload each time the user browses to a new image. This javascript way of browsing allows for much quicker navigation between images and provides a much more smooth and pleasing experience from the users perspective.

### Rationale
Galleries have been heavily used by media sites relying on banner impressions for a living to get as many pageviews out of the user as possible. A gallery with 20 images that shows in separate page views yields a much bigger returns in banner impressions than having an article with 20 images beneath each other. However, as the javascript galleries, where only part of the page is reloaded, becomes increasingly more popular, the days of the gallery with separate page loads seems more and more outdated. If you are still aiming for as many banner impressions as possible, consider having the banners change as well for every time the user browses to a new image.

### Usage Examples
A gallery consists of multiple images that can be browsed one by one by navigating between them. Only one image is viewed at a time. Often, several different options for navigating the gallery is provided in order to accommodate  several different browsing behaviors of the different kinds of users browsing the gallery. It is common for a gallery to display the context the current image image being views as in Image 2 out of 18 images, the shorter 2 out of 18, or merely 2/18.
Navigation options often include

	Previous and next image buttons
	A series of thumbnail images arranged in one of the following ways:
	
		Previous- and next images with links to these images
		The 2 or 3 of the nearest images (previous 2 or 3 and next 2 or 3 images) with links to these images
		A list of all images in the gallery arranged in a grid  often with 3, 4, or 5 images in each row.
	
	A text link after the image caption text saying Next image, Next, or the title of the next image.
	Tabs with image numbers linking to each image in the gallery.
	Clicking the current image itself tend to yield one of two effects: (1) Zoom the image or (2) navigate to the next image
	Keyboard arrow key listeners: left arrow fires a show previous image event, right arrow fires a show next image event.

Tips for designing a gallery
Provide thumbnails and numbers
Thumbnails allow the user to find out where he or she is in the gallery: the context of the current image. Thumbnails also provide a great way to keep the user in the flow of going to the next image; if the image seems interesting in thumbnail mode it might be worth a click from the users perspective.
Listing the gallery images as numbers allows for quick navigation. Highlight the current image to let the user know where he or she is in the gallery: the context of the current image.
Decide on auto (slideshow) or manual (or both)
Galleries (or slideshows) work in one of two ways: either they switch automatically from image to image after a set time interval, or buttons and other navigation elements are provided to let the user browse through images manually. Some galleries provide pause buttons and thus provides a mix between the two.
Reload the entire page or change only the important parts
Newer galleries tend to be based on javascript where only the image, its context, captions, and comments are changed as opposed to having a complete page reload each time the user browses to a new image. This javascript way of browsing allows for much quicker navigation between images and provides a much more smooth and pleasing experience from the users perspective.

---

## Good Defaults

**URL Validation:** https://ui-patterns.com/patterns/GoodDefaults

### Problem Summary
The user needs to enter data into the system, where some input values are most likely to match default values.

### Solution
Pre-fill form fields with best guesses at what the user wants.
Drop down boxes and text fields are prefilled or preselected with reasonable default values. The default values are intelligent guesses as to what the user would possibly select.
When appropriate, reduce the cognitive load on users by pre-filling forms with default values. Use contextual information to make intelligent guesses as to what the user would most likely select. Do so only when you are reasonably sure your users would agree with your default values – otherwise, you will create extra work. Pre-filling controls to your own benefit rather than your users will most often backfire.

### Rationale
By providing default values in often complex forms with many choices, you save the user from the hassle of selecting all the relevant choices. Filling out a long form can sometimes be enough reason for the user to go somewhere else, where the process is easier.
The default values might not be right, but at least you provided the user with an example that he can change with as much effort as he would have put in if there was no example.

### Usage Examples
Pre-fill form fields with best guesses at what the user wants.
Drop down boxes and text fields are prefilled or preselected with reasonable default values. The default values are intelligent guesses as to what the user would possibly select.
When appropriate, reduce the cognitive load on users by pre-filling forms with default values. Use contextual information to make intelligent guesses as to what the user would most likely select. Do so only when you are reasonably sure your users would agree with your default values – otherwise, you will create extra work. Pre-filling controls to your own benefit rather than your users will most often backfire.

---

## Guided Tour

**URL Validation:** https://ui-patterns.com/patterns/Guided-tour

### Problem Summary
The user wants to learn about new or unfamiliar interface features.

### Solution
“Just-in-time” guidance is triggered as the user explores.
Allow users to learn at their own pace using tooltips, overlays, models, and alerts hinting optimal use of an interface within the context of everyday use. Connect hints with clear completion states. Too many and too plain hints lead to frustration. Dont overdo it and be sure to allow escape.
Create a series of individual hints that progressively appear during the first-time use of a product or interface. Hints can be anything from tooltips, overlays, to modal alerts.
Some users appreciate the help and others dont. Be sure to always allow escape; to dismiss your guided tour.
Product-guided vs User-guided.
Decide whether you want to let the tour be product guided or user-guided. In a product-guided tour, hints are automatically progressed in linear succession, while hints in a user-guided tour are triggered as the user reaches appropriate points in their experience. For user-guided tours, hints may appear in different orders for different users.

### Usage Examples
“Just-in-time” guidance is triggered as the user explores.
Allow users to learn at their own pace using tooltips, overlays, models, and alerts hinting optimal use of an interface within the context of everyday use. Connect hints with clear completion states. Too many and too plain hints lead to frustration. Dont overdo it and be sure to allow escape.
Create a series of individual hints that progressively appear during the first-time use of a product or interface. Hints can be anything from tooltips, overlays, to modal alerts.
Some users appreciate the help and others dont. Be sure to always allow escape; to dismiss your guided tour.
Product-guided vs User-guided.
Decide whether you want to let the tour be product guided or user-guided. In a product-guided tour, hints are automatically progressed in linear succession, while hints in a user-guided tour are triggered as the user reaches appropriate points in their experience. For user-guided tours, hints may appear in different orders for different users.

---

## Home Link

**URL Validation:** https://ui-patterns.com/patterns/HomeLink

### Problem Summary
The user needs to go back to a safe start location of the site.

### Solution
Create a link to the starting point or front page of the website on the sites logo on every single page on the website.
	If the site does not have a logo, then create a link to the front page of the website with the text ‘Home’.
	The link and/or linked images should always be in the same location on all pages.
	If the website has more than one home, then be sure to make the distinction in linking between the root home and the local home.

### Rationale
It has become a standard in webdesign, that the sites logo is always linked to a safe start location for the user. Normally, this is the front page of the site, but it could also be the front page of a section in the site, or some other safe start location for the user.

### Usage Examples
Create a link to the starting point or front page of the website on the sites logo on every single page on the website.
	If the site does not have a logo, then create a link to the front page of the website with the text ‘Home’.
	The link and/or linked images should always be in the same location on all pages.
	If the website has more than one home, then be sure to make the distinction in linking between the root home and the local home.

---

## Horizontal Dropdown Menu

**URL Validation:** https://ui-patterns.com/patterns/HorizontalDropdownMenu

### Problem Summary
The user needs to navigate among sections of a website, but space to show such navigation is limited.

### Solution
A list of main sections are displayed as links in a single vertical strip. When a user hovers their cursor over a list item or clicks a list item, a sub list is displayed (usually adjacent and below). The user can then follow the now horizontally extended list item down, and select the subsection they are interested in.
Traditionally, when the user’s cursor leaves a drop down menu, the menus are no longer visible. However, this is an unforgiving interaction method.
As humans, we do not always act perfectly as the system would like us to. To cope with human errors and to guide us to act as you would like us to, you can implement the following:

	On mouseout events (when the user takes his mouse away from the drop-downed box), add a delay before hiding the drop-downed box (typically 200-300 ms.)
	Make the area of each menu item wider than just the text of the menu item so that the user has more space to put his mouse cursor over.
	Change the cursor image as the user hovers over a list item.

Other issues you want to take notice of
There are many different kinds of drop-down menus out there. Some are purely javascript. These kinds of drop-down menus do not work well with search engines. To let the search engines index your page, you would want to have the menu formatted in HTML from the beginning of the page load, rather than building it in javascipt client-side after the page has loaded.

### Rationale
Drop-down menus save space by organising and concealing information. Drop-down menus are not regarded as a technique that increases usability, as they can often be difficult to use.
Flyout menus allow for only showing top levels of the page’s hierarchy permanently, while still giving the option to show deeper levels on mouse over

### Usage Examples
A list of main sections are displayed as links in a single vertical strip. When a user hovers their cursor over a list item or clicks a list item, a sub list is displayed (usually adjacent and below). The user can then follow the now horizontally extended list item down, and select the subsection they are interested in.
Traditionally, when the user’s cursor leaves a drop down menu, the menus are no longer visible. However, this is an unforgiving interaction method.
As humans, we do not always act perfectly as the system would like us to. To cope with human errors and to guide us to act as you would like us to, you can implement the following:

	On mouseout events (when the user takes his mouse away from the drop-downed box), add a delay before hiding the drop-downed box (typically 200-300 ms.)
	Make the area of each menu item wider than just the text of the menu item so that the user has more space to put his mouse cursor over.
	Change the cursor image as the user hovers over a list item.

Other issues you want to take notice of
There are many different kinds of drop-down menus out there. Some are purely javascript. These kinds of drop-down menus do not work well with search engines. To let the search engines index your page, you would want to have the menu formatted in HTML from the beginning of the page load, rather than building it in javascipt client-side after the page has loaded.

---

## Illusion of control

**URL Validation:** https://ui-patterns.com/patterns/Illusion-of-control

### Problem Summary
We have a tendency to believe that outcomes can be controlled, or at least influenced, when they clearly cannot.

### Solution
Provide your users with a sense of control in order to let them feel confident and assured that they their actions have a positive influence on their goals.

### Rationale
As humans, we have a desire to believe that we are in control and thus have a tendency to believe that outcomes can be controlled, or at least influenced, when they clearly cannot.
We believe in the illusion that we can control factors outside our reach; that actions we take to influence them are directly linked to how things turn out.
If we tell ourselves that we are not being loved as we are not good enough, we believe we can get the love we want by striving for being good enough. We tell ourselves that things will turn out for the better if we live a good life and worship our god(s). We tell ourselves that somebody is not attracted to us because we are overweight, have weird teeth, or have too little breasts, why manipulating these factors will change the opinion of others. We tell ourselves that we are in control over facebooks privacy settings although they are too confusing to let us actually be in control. We tell ourselves that the reason we did not get a certain job was because we are not smart enough why we study harder.
The illusion of control can act as a motivational factor for conducting certain behavior that is either unsafe or that we believe will bring us closer to a goal.
Optimistic self-appraisals of our capabilities that are not completely apart from what is possible can be advantageous. On the other side can  judgments far fetched from the truth turn out to be self-limiting.
The illusion of control gives us a sense of power and in turn happiness. When we believe we are in control, we do not have to rationally analyze facts in order to make a decision. The illusion of control drives us forward and can help escalate commitment.
Illusory beliefs about control help us strive for reaching goals, but are not contributing to sound rational decision-making. Instead they can cause insensitivity to feedback, hinder learning, and make us more risk seeking as subjective risk is reduced by the illusion of control1.

### Usage Examples
Provide your users with a sense of control in order to let them feel confident and assured that they their actions have a positive influence on their goals.

---

## Image Zoom

**URL Validation:** https://ui-patterns.com/patterns/ImageZoom

### Problem Summary
The user wants to zoom in on an image to view the details in a higher image resolution.

### Solution
Provide a mechanism that allows the user to zoom an image to view its details.
From a server point of of view, an important goal is not to pre-load high resolution images before they are requested. This will help save bandwidth.
An intuitive way of doing this is to allow the user to click a spot on a given image. As the user clicks the image to zoom, a higher resolution image is preloaded.
Provide graphics or text about zooming in on the image; a bare image will not suggest zoom functionality to the user in itself.

### Rationale
Allowing the user to zoom in on an image permits exploration of the images details. Depending on the zoom factor, showing the entire high resolution image from the beginning will not provide the user with an overview of the entire image thus removing the context of the details viewed.
By providing a zoom functionality, a user can zoom into just one area of the image that he or she is interested in. In this way, the user is not bothered by the other details.

### Usage Examples
Provide a mechanism that allows the user to zoom an image to view its details.
From a server point of of view, an important goal is not to pre-load high resolution images before they are requested. This will help save bandwidth.
An intuitive way of doing this is to allow the user to click a spot on a given image. As the user clicks the image to zoom, a higher resolution image is preloaded.
Provide graphics or text about zooming in on the image; a bare image will not suggest zoom functionality to the user in itself.

---

## Inline Help Box

**URL Validation:** https://ui-patterns.com/patterns/InlineHelpBox

### Problem Summary
The user needs assistive information located close to the interaction they are about to perform.

### Solution
Document your interface in-line with descriptive help blocks. If important information needs to be communicated to the user, it can be easily explained with an inline help box located above or below the main content of a screen.
The inline help box needs to be differentiated from normal content. As the help box itself is not part of the main functionality, it is a good idea to add a style to it that visually separates the help box from that functionality. An easy way to do this is by applying another background and font color to the help box.
Additionally, to avoid the users discontent with the help box, a great feature of the in-line help box is to have a hide this box functionality. Once the user has clicked this link, the help box will never be shown to the user again.
However, you might want to provide an option for the user to re-enable all help boxes, to allow the user to get that first-hand help that he or she started out getting.

### Rationale
Providing your users with assistive information, located close to an interaction, makes accessing and consuming instructional info simple and easy. In Line help boxes are far more engaging than reading disconnected FAQ’s or help sections.
By allowing the user to easily close/hide each help box, the user is not bothered with unnecessary information once it has been understood.

### Usage Examples
Document your interface in-line with descriptive help blocks. If important information needs to be communicated to the user, it can be easily explained with an inline help box located above or below the main content of a screen.
The inline help box needs to be differentiated from normal content. As the help box itself is not part of the main functionality, it is a good idea to add a style to it that visually separates the help box from that functionality. An easy way to do this is by applying another background and font color to the help box.
Additionally, to avoid the users discontent with the help box, a great feature of the in-line help box is to have a hide this box functionality. Once the user has clicked this link, the help box will never be shown to the user again.
However, you might want to provide an option for the user to re-enable all help boxes, to allow the user to get that first-hand help that he or she started out getting.

---

## Inplace Editor

**URL Validation:** https://ui-patterns.com/patterns/InplaceEditor

### Problem Summary
The user needs to quickly and easily edit a value on a page

### Solution
Let users edit values in the same place as they are displayed. Provide an easy way to let users edit parts of a page without having to be redirected to an edit page. Typically, hover effects are used to invite editing.
The Inplace Editor pattern allows for localized editing of elements on the fly. The pattern provides ease of editing by placing the controls right next to the elements they affect.
For example, when in editing mode of an application, a page title element will display editing controls when the user hovers their mouse over it. The elements background color is highlighted and a tooltip is shown prompting the user to click the element to edit it. Once the user clicks the element, it is transformed into an input field (text, dropdown, etc.). A save button and a cancel button are also displayed. Often, the input field matches the styling of the original element. If the original element was a header written in size 20pt, the size of the font in the input field would also be 20pt. This styling is mirrored to ensure that the user can connect the original element with the new editable
The user can then edit the value of the input field (which is the same as the original elements value) and click save or cancel. If ‘save’ is clicked, the value is saved through an AJAX call to the underlying database, the value of the element is updated and the element is returned to normal view. If cancel is clicked, the element is changed back to the original view without any changes.
This pattern is often combined with AJAX techniques, which is an asynchronous call to the server through javascript that does not require a refresh of the page. There are many javascript libraries available online that deliver ready-to-use inplace editors.

### Rationale
An in-place editor provides an easy way to let the user edit parts of a page without having to be redirected to an edit page. Instead, the user can just click around on a page and edit the elements he or she wishes to change – without reloading the page.

### Usage Examples
Let users edit values in the same place as they are displayed. Provide an easy way to let users edit parts of a page without having to be redirected to an edit page. Typically, hover effects are used to invite editing.
The Inplace Editor pattern allows for localized editing of elements on the fly. The pattern provides ease of editing by placing the controls right next to the elements they affect.
For example, when in editing mode of an application, a page title element will display editing controls when the user hovers their mouse over it. The elements background color is highlighted and a tooltip is shown prompting the user to click the element to edit it. Once the user clicks the element, it is transformed into an input field (text, dropdown, etc.). A save button and a cancel button are also displayed. Often, the input field matches the styling of the original element. If the original element was a header written in size 20pt, the size of the font in the input field would also be 20pt. This styling is mirrored to ensure that the user can connect the original element with the new editable
The user can then edit the value of the input field (which is the same as the original elements value) and click save or cancel. If ‘save’ is clicked, the value is saved through an AJAX call to the underlying database, the value of the element is updated and the element is returned to normal view. If cancel is clicked, the element is changed back to the original view without any changes.
This pattern is often combined with AJAX techniques, which is an asynchronous call to the server through javascript that does not require a refresh of the page. There are many javascript libraries available online that deliver ready-to-use inplace editors.

---

## Input Feedback

**URL Validation:** https://ui-patterns.com/patterns/InputFeedback

### Problem Summary
The user has entered data into the system and expects to receive feedback on the result of that submission.

### Solution
When users submit content to your site via forms, errors in the are bound to happen from time to time. The goal of this pattern is to improve the user experience by minimizing input errors.
A paradigm called data validation is well suited for catching errors at the time of submitting a form. A common way to tell if data validates is to set up rules for each input field in the form. The data entered must pass these rules to be considered valid. Such validation rules can be:

	Validate presence of content  at least some content must be entered
	Validate exclusion of content  prohibited values  for instance inserting admin as username
	Validate inclusion of content  data must contain certain data or must be within a certain range
	Validate acceptance (of for instance terms of service)  often with a checkbox
	Validate confirmation  two input fields needs to match  seen with for instance passwords
	Validate format  an email for instance needs an @ sign and a number of dots
- for instance that the user must be above 18 year of age.
	Validate length  A password must in many cases be at least 6 characters long.
	Validate uniqueness  Many systems only allow one user with a given username

If the data submitted by the user validates, it is good practice to let the user know that everything went as planned. Even better, redirect the user to a page, where he or she can see the newly submitted content in a context.
However, if the data submitted by the user does not validate, an error message should be presented to the user explaining how to correct the data and request for a re-submit. Such an error message should explain that:

	An error has occurred. Display box at the top of the page (so that the user does not need to scroll the page to find out that an error occurred), preferably colored red to signal an error.
	Where the error occurred. This can be done by listing the fields that caused the error in the error message, as well as highlighting the fields (by changing their colors) that caused the error.
	How the error can be repaired. Provide information on what needs to be different in order for the field to validate. This can either be listed in the top error box or directly next to the field causing the error.

The visual representation of the input feedback should correspond with the message you want to give. If the submission went successfully, consider letting the user know in a green box. If the message is neutral, a color often used is yellow. If something went wrong, red is often used. But beware  red means danger  is the user experiencing a dangerous situation?

### Rationale
As the user fills out a form on a web page, he or she is conducting the process of converting mental data structured in one way to a written form structured in another way. As all humans do not think alike, we are bound to enter the data in different ways as we try to convert our individually structured data to a shared structure defined by the system.
Data entered in web forms is prone to contain errors, which we must be prepared for in our design. The user must be made aware of the fact that the data entered did not match the structure that we designed for. Using visually distinct feedback notices, the user will be made aware of such errors and how to correct them.

### Usage Examples
When users submit content to your site via forms, errors in the are bound to happen from time to time. The goal of this pattern is to improve the user experience by minimizing input errors.
A paradigm called data validation is well suited for catching errors at the time of submitting a form. A common way to tell if data validates is to set up rules for each input field in the form. The data entered must pass these rules to be considered valid. Such validation rules can be:

	Validate presence of content  at least some content must be entered
	Validate exclusion of content  prohibited values  for instance inserting admin as username
	Validate inclusion of content  data must contain certain data or must be within a certain range
	Validate acceptance (of for instance terms of service)  often with a checkbox
	Validate confirmation  two input fields needs to match  seen with for instance passwords
	Validate format  an email for instance needs an @ sign and a number of dots
- for instance that the user must be above 18 year of age.
	Validate length  A password must in many cases be at least 6 characters long.
	Validate uniqueness  Many systems only allow one user with a given username

If the data submitted by the user validates, it is good practice to let the user know that everything went as planned. Even better, redirect the user to a page, where he or she can see the newly submitted content in a context.
However, if the data submitted by the user does not validate, an error message should be presented to the user explaining how to correct the data and request for a re-submit. Such an error message should explain that:

	An error has occurred. Display box at the top of the page (so that the user does not need to scroll the page to find out that an error occurred), preferably colored red to signal an error.
	Where the error occurred. This can be done by listing the fields that caused the error in the error message, as well as highlighting the fields (by changing their colors) that caused the error.
	How the error can be repaired. Provide information on what needs to be different in order for the field to validate. This can either be listed in the top error box or directly next to the field causing the error.

The visual representation of the input feedback should correspond with the message you want to give. If the submission went successfully, consider letting the user know in a green box. If the message is neutral, a color often used is yellow. If something went wrong, red is often used. But beware  red means danger  is the user experiencing a dangerous situation?

---

## Input Prompt

**URL Validation:** https://ui-patterns.com/patterns/InputPrompt

### Problem Summary
The user needs to enter data into the system

### Solution
An input field is pre-filled with example text or a question that prompts the user with what to do or type.
The Input Prompt pattern is most successfully used with dropdown lists and text fields. As dropdown lists have a fixed set of choices, words like Select or Choose are used for prompts. For text fields, the prompting string often begins with a call to action: Enter, Type, Search. End the string with the noun the input is describing, for instance Enter city or Enter an address.
Text fields use the Input Prompt pattern combined with scripting to remove the prompt text from a field, when the user’s focus is set. Once the user enters the input field to type in content, the prompting text is removed and replaced with nothing so that the input field is free for the user to fill out.

### Rationale
When a user fills out a form it is most often with the purpose of filling it out as quickly as possible to get on with the service offered. This is why the user often just scans through form fields and labels without giving the labels much of a glance. By using input prompts, immediate attention is drawn to what the user needs to fill in. The user can’t miss it. Although you must beware of removing labels entirely, as the input prompt is removed once focus has been set to the text field.
Input prompt is often used for small forms that are key to the core functionality of a site as inserting the label inside the text field itself helps save space. For more elaborate forms, there is often more than enough room available to explain each input field.

### Usage Examples
An input field is pre-filled with example text or a question that prompts the user with what to do or type.
The Input Prompt pattern is most successfully used with dropdown lists and text fields. As dropdown lists have a fixed set of choices, words like Select or Choose are used for prompts. For text fields, the prompting string often begins with a call to action: Enter, Type, Search. End the string with the noun the input is describing, for instance Enter city or Enter an address.
Text fields use the Input Prompt pattern combined with scripting to remove the prompt text from a field, when the user’s focus is set. Once the user enters the input field to type in content, the prompting text is removed and replaced with nothing so that the input field is free for the user to fill out.

---

## Intentional Gaps

**URL Validation:** https://ui-patterns.com/patterns/Intentional-gaps

### Problem Summary
Create intentional gaps that users cant help but try to fill

### Solution
Leave deliberate gaps that users will want to fill. We are motivated to complete the incomplete. The closer to completion users perceive a task to be, the more motivated they are to finish it.

	Create obvious gaps. Leave deliberate gaps that users will want to fill. By choosing what gaps to fill and which not to fill, you are framing decisions around a predefined context and allow directing users toward predefined decision paths that allow for persuasion along the way.
	Finish the sentence. Make forms read like a sentence, letting users fill out the blanks. Making forms linguistically fluent, its context is easier to understand and inputs are more effortlessly selected.
	Instill a sense of autonomy. Provide good momentum by laying out the first foundational blocks paving the way for a flying start. Give users the freedom to complete your intentional gaps with creativity to boost their sense of autonomy and control.

### Rationale
The feeling of seeing something out of order or incomplete creates a feeling of stress that we want to alleviate. This in turn motivates us to either remove or reduce the discomfort by filling in the missing gaps or fixing what is wrong. The more obvious and easy it is for users to complete the intentional gap, the more likely users are to engage.

### Usage Examples
Leave deliberate gaps that users will want to fill. We are motivated to complete the incomplete. The closer to completion users perceive a task to be, the more motivated they are to finish it.

	Create obvious gaps. Leave deliberate gaps that users will want to fill. By choosing what gaps to fill and which not to fill, you are framing decisions around a predefined context and allow directing users toward predefined decision paths that allow for persuasion along the way.
	Finish the sentence. Make forms read like a sentence, letting users fill out the blanks. Making forms linguistically fluent, its context is easier to understand and inputs are more effortlessly selected.
	Instill a sense of autonomy. Provide good momentum by laying out the first foundational blocks paving the way for a flying start. Give users the freedom to complete your intentional gaps with creativity to boost their sense of autonomy and control.

---

## Kairos

**URL Validation:** https://ui-patterns.com/patterns/Kairos

### Problem Summary
Communicate to users in situations that are the opportune moments for change

### Solution
Kairos is a passing instant when an opening appears which must be driven through with force if success is to be achieved2. Kairos are situations of change.
Kairos occur in many situations  some are random but others come in patterns. One such pattern is when a user exits one group to join another. Such situations are potentially valuable as they represent moments where users are open and receptive to making a deal or making a behavior change.
From an advertising and e-commerce perspective, karios situations are great open opportunities to tailor specific messages and offers to users.
Kairos are moments to strike! Your chance of success in delivering your message to the user is far better when you utilize Kairos than just any time.
Kairos comes in patterns
Patterns of change
A good place to look for patterns are when larger changes occur. Look for patterns of change. Direct your attention when users are ready to buy their first car, move away from home, buy their first home, buy their first furniture, return their first furniture, when their first baby is born, and when their baby is moving away from home. These are events happening only once for the individual, but all the time for users when seen as a community.
Patterns of recurring behavior
We have a tendency to conduct the same behavior over and over again. We make the same mistakes again and again, shop the same places, and repeat the same decisions. Its just easier and more comforting than spending energy on making a rational informed decision  or changing behavior. These tendencies form patterns of recurring behavior that can act as opportunities for you to tailor messages and offers that make it easier for users to conduct their regular habits.
Map it out
Map out what situations of change and recurring behavior that you can possibly support and build experiences to support them.

	Map patterns of change. Map patterns of opportune moments across your user base. Typically such moments are in situations of change or transition. These moments are potentially valuable as they represent moments where users are open and receptive to making a deal or changing a behavior.
	Map patterns of recurring behavior. We tend to conduct the same behavior over and over again. We make the same mistakes, shop the same places, and repeat the same decisions. Consider these moments opportunities to tailor messages and offers making it easier for users to conduct routine.
	Map seasonal patterns. Seasons and traditions come in patterns where we consider a fresh start. Be it new years resolutions or the summer holiday where we reconsider our life.

### Rationale
Kairos is ancient greek for the right, critical, or opportune moment for action. It is the passing instant when an opening appears, which must be driven through with fource if success is to be achieved. Relevance, recent events, and who the audience is plays a role in determining the right moment to act. Map them ot.
Kairos represents situations of change. Situations of change are potentially valuable because they represent moments where users are open and receptive to making a deal or changing a behavior.
By striking at the exact right time, the chances of successfully being effective in delivering your message an in turn create sales, change behavior, or in other way influence users decisions are much larger than striking at any other time.
Utilizing Kairos is a step away from broadcasting your message to everybody all the time toward tailoring your message to the individual at the right time. The same message is relevant to different people at different opportune moments.

### Usage Examples
Kairos is a passing instant when an opening appears which must be driven through with force if success is to be achieved2. Kairos are situations of change.
Kairos occur in many situations  some are random but others come in patterns. One such pattern is when a user exits one group to join another. Such situations are potentially valuable as they represent moments where users are open and receptive to making a deal or making a behavior change.
From an advertising and e-commerce perspective, karios situations are great open opportunities to tailor specific messages and offers to users.
Kairos are moments to strike! Your chance of success in delivering your message to the user is far better when you utilize Kairos than just any time.
Kairos comes in patterns
Patterns of change
A good place to look for patterns are when larger changes occur. Look for patterns of change. Direct your attention when users are ready to buy their first car, move away from home, buy their first home, buy their first furniture, return their first furniture, when their first baby is born, and when their baby is moving away from home. These are events happening only once for the individual, but all the time for users when seen as a community.
Patterns of recurring behavior
We have a tendency to conduct the same behavior over and over again. We make the same mistakes again and again, shop the same places, and repeat the same decisions. Its just easier and more comforting than spending energy on making a rational informed decision  or changing behavior. These tendencies form patterns of recurring behavior that can act as opportunities for you to tailor messages and offers that make it easier for users to conduct their regular habits.
Map it out
Map out what situations of change and recurring behavior that you can possibly support and build experiences to support them.

	Map patterns of change. Map patterns of opportune moments across your user base. Typically such moments are in situations of change or transition. These moments are potentially valuable as they represent moments where users are open and receptive to making a deal or changing a behavior.
	Map patterns of recurring behavior. We tend to conduct the same behavior over and over again. We make the same mistakes, shop the same places, and repeat the same decisions. Consider these moments opportunities to tailor messages and offers making it easier for users to conduct routine.
	Map seasonal patterns. Seasons and traditions come in patterns where we consider a fresh start. Be it new years resolutions or the summer holiday where we reconsider our life.

---

## Lazy Registration

**URL Validation:** https://ui-patterns.com/patterns/LazyRegistration

### Problem Summary
The user wants to immediately use you and try your website without conducting a formal registration beforehand

### Solution
Allow users to access a limited set of features, functionality, or content before or without registrering.
Let users interact enough with your system so that an actual registration is just another small step in a larger process: a small step, not an obligation.
The light version of this pattern is the shopping cart of an e-commerce site, where the user can accumulate relevant products in a cart and then in turn register an account if he or she chooses to make a purchase.
In the heavier version of this pattern, an anonymous user account is immediately created for the user  full with an auto-generated database ID and a complimenting cookie with the accounts ID that will ensure that the users details and the information he or she has entered will be remembered upon the next visit. With appropriate intervals, inactive anonymous accounts are cleared from the database in order to not clutter it up.
As the user interacts with the system, data is accumulated to the account. While some data might not be shown to the user other kinds of data will. It is the latter kind of data that in turn will make the user register  the visible evidence that the user has invested energy into using the system. A smart way to gather such data is to expose holes of data that the user can populate.
Two such holes are the username and password: the two bits of information that will allow the user to log into his account from more than one computer.

### Rationale
Deliver value before prompting for conversion. Shopping carts are a classic pattern that plays on Lazy Registration: users can browse and choose products, but only have to register when they proceed to check out.x
The Lazy Registration pattern allow users to use your system and take action before or without registrering. The idea is to let users interact enough with your system so that the actual registration is just another small step in the larger process. Its a small step  not an obligation. The classic Shopping Cart pattern is a good example of Lazy Registration: users can browse and choose products and only have to register when they proceed to check out.
For this pattern to work, you need to provide the users with an incentive to give you the registration data you are looking for. You need to provide a worthwhile service to your users for them to give you their data back in return. You want to use classic Carrot and stick motivation  and just as important: communicate the benefit you are providing. If the registration data you are looking for with the user is sensitive, you must be able to assure your users that their data will be safe and secure.

### Usage Examples
Allow users to access a limited set of features, functionality, or content before or without registrering.
Let users interact enough with your system so that an actual registration is just another small step in a larger process: a small step, not an obligation.
The light version of this pattern is the shopping cart of an e-commerce site, where the user can accumulate relevant products in a cart and then in turn register an account if he or she chooses to make a purchase.
In the heavier version of this pattern, an anonymous user account is immediately created for the user  full with an auto-generated database ID and a complimenting cookie with the accounts ID that will ensure that the users details and the information he or she has entered will be remembered upon the next visit. With appropriate intervals, inactive anonymous accounts are cleared from the database in order to not clutter it up.
As the user interacts with the system, data is accumulated to the account. While some data might not be shown to the user other kinds of data will. It is the latter kind of data that in turn will make the user register  the visible evidence that the user has invested energy into using the system. A smart way to gather such data is to expose holes of data that the user can populate.
Two such holes are the username and password: the two bits of information that will allow the user to log into his account from more than one computer.

---

## Levels

**URL Validation:** https://ui-patterns.com/patterns/Levels

### Problem Summary
Use levels to communicate progress and gauge users’ personal development

### Solution
Consider how you can partition your system into levels of increasing difficulty, powers, and features in order to keep users engaged, away from boredom, and provided with a sense of accomplishment.

	Provide appropriate challenges. In videogames, a sequence of gradually more challenging levels help to maintain the balance between the rising skill level of users as they get accustomed to the game. Consider how you can gradually expose functionality requiring more expert knowledge.
	Let users choose the difficulty level. Videogames often let players choose to play on easy, medium or hard modes so that they can quickly find the appropriate challenge. Consider allowing users access advanced modes or hide advanced functionality with progressive disclosure.
	Reward users with completion. Break up a larger learning journey into smaller wins. First level is to complete the profile, second level is to create the first project, third is to invite collaborators.

### Rationale
As users progress, so does their skill level, requiring increasingly more difficult challenges. Consider how you can partition your system into levels of increasing difficulty, powers, and features in order to keep users engaged, away from boredom, and provided with a sense of accomplishment.

### Usage Examples
Consider how you can partition your system into levels of increasing difficulty, powers, and features in order to keep users engaged, away from boredom, and provided with a sense of accomplishment.

	Provide appropriate challenges. In videogames, a sequence of gradually more challenging levels help to maintain the balance between the rising skill level of users as they get accustomed to the game. Consider how you can gradually expose functionality requiring more expert knowledge.
	Let users choose the difficulty level. Videogames often let players choose to play on easy, medium or hard modes so that they can quickly find the appropriate challenge. Consider allowing users access advanced modes or hide advanced functionality with progressive disclosure.
	Reward users with completion. Break up a larger learning journey into smaller wins. First level is to complete the profile, second level is to create the first project, third is to invite collaborators.

---

## Liking

**URL Validation:** https://ui-patterns.com/patterns/Liking

### Problem Summary
We prefer to say yes to the requests of someone we know and like

### Solution
Liking of you and your products depend on a series of things. Those listed below are summed up from Cialdinis book: Influence1.

	Physical attractiveness
	Similarity
	Compliments
	Contact
	Cooperation rather than competition
	Conditioning  association

Physical attractiveness
It is generally acknowledged that good-looking people have an advantage in social interactions. A sort of halo effect occurs when one positive characteristic of a person dominates the way that person is viewed by others. Research has shown that we automatically assign favorable traits as talent, kindness, honesty, and intelligence to good-looking people1. The same is true for a good-looking product. Attractive things work better2. As does good-looking web design.

Which is do you think is more attractive? The website of Demerara  Eldorado Rum or the website of DonQ Rum? We assign favorable traits to attractive things and look past less attractive traits. Research has shown that attractive things clearly work betterwork better2!
Similarity
We tend to favor people with similar backgrounds and interests. Find a way to either assure your users that you are like them, or that your users are similar to them. Testimonials from people with the same problems, backgrounds, or interest can help spark liking you.

Corkd.com explains why you should sign up by saying â€œinteract and share with your drinking buddiesâ€. You can interact about wine with people of similar interests (wine).
Compliments
We are big suckers for flattery. Even when we are completely aware that its impersonal, clearly false, and designed only to convert us, we tend to believe praise and to like those who provide it. Compliments and praise automatically produces a positive reaction that makes easily makes us fall victim to obvious attempts to win our favor1.

We are suckers for flattery. As people like our posts on facebook and we get more followers on twitter, we feel motivated to write and ourselves engage more to receive even more flattery.
Contact
Contact between people who would normally dislike each other can increase likening and understanding between the two, depending on the experience. A positive experience leads to a higher familiarity and liking while a distasteful one produces the opposite effect.
Mass chat communities like those generated by IRC has brought people together that would normally never get a chance to talk. Even though the chat might not have been about breaking down boundaries, meeting and talking to people not similar to ourselves increase our liking of the group those people represent.
Cooperation rather than competition
We like people and things that are familiar to us or seems like us, as we can identify with them. We also have a tendency to dislike people and things that are not familiar and do not seem like us.
Once competition between people starts, this effect is enhanced. Competition makes us stick with what we know and distance ourselves from what we dont.
Cooperation on the other has a dampening effect. Cooperation with people who are not like us can help us like them more. Even a vague understanding of a cooperation taking place will help. Use cooperation to increase liking between groups that a far apart. Point out cooperation in a situation when it exists naturally. Amplify cooperation when it exists only weakly. Try to manufacture it when it is absent. Can you create a feeling of us against the system, that we pull together for mutual benefit, or that you work together with your users to get them to kick ass?
On the other hand, competition can help companies make you dislike their competitors, and make you love their own company more.
Apples Mac vs. PC campaign played on the long-time rivalry and competition between Macs and PCs. It helped start and spark a bond between Mac owners that PC owners never had  a connection with one simple Apple-favored message: PC is bad, Mac is good. Brilliant execution!
Conditioning  association
We have a tendency to try to bask in reflected glory by what and who we associate and connect ourselves with. We try to connect ourselves to success by using the pronoun we and distance ourselves from losers by using they. It works. Connect yourself or your products with things your users like to increase liking.

The specialized instrument microphone company, Applied Microphone Technology spends large amounts of energy and money to endorse famous and respected artists who use their product. This is an attempt let the liking of the endorsed artists fall back on the microphone company because of the association.

### Rationale
People respond not only to the message, but the messenger, and thats you. Being likable attracts. Being unlikable repels. Demonstrate a positive attitude. Be positive rather than negative, and encourage rather than criticize.
We are receptive towards messages from what and who we like to such and extend that facebook designed one of its key features around this: fan pages. You can choose to like a fan page and in turn subscribe to posts from that page. It is a feature both popular among users but even more popular among fan page owners, as it leverages the very persuasive principle of Liking1.
We respond much more favorably to people and things we like and know than those we either do not like or are not familiar with. This fact can be used to increase the likelihood of strangers complying to your requests.
When a stranger tells us that a friend of ours suggested we could help, we have a hard time rejecting the person  even though he or she is a total stranger. Turning away a person under those circumstances is difficult  its almost like rejecting the friend!
We are quick to point out flaws of political candidates of the opposition, but have a tendency to look through failures of who we root for. The more we like people and things, the more open we are to complying with what they communicate.

### Usage Examples
Liking of you and your products depend on a series of things. Those listed below are summed up from Cialdinis book: Influence1.

	Physical attractiveness
	Similarity
	Compliments
	Contact
	Cooperation rather than competition
	Conditioning  association

Physical attractiveness
It is generally acknowledged that good-looking people have an advantage in social interactions. A sort of halo effect occurs when one positive characteristic of a person dominates the way that person is viewed by others. Research has shown that we automatically assign favorable traits as talent, kindness, honesty, and intelligence to good-looking people1. The same is true for a good-looking product. Attractive things work better2. As does good-looking web design.

Which is do you think is more attractive? The website of Demerara  Eldorado Rum or the website of DonQ Rum? We assign favorable traits to attractive things and look past less attractive traits. Research has shown that attractive things clearly work betterwork better2!
Similarity
We tend to favor people with similar backgrounds and interests. Find a way to either assure your users that you are like them, or that your users are similar to them. Testimonials from people with the same problems, backgrounds, or interest can help spark liking you.

Corkd.com explains why you should sign up by saying â€œinteract and share with your drinking buddiesâ€. You can interact about wine with people of similar interests (wine).
Compliments
We are big suckers for flattery. Even when we are completely aware that its impersonal, clearly false, and designed only to convert us, we tend to believe praise and to like those who provide it. Compliments and praise automatically produces a positive reaction that makes easily makes us fall victim to obvious attempts to win our favor1.

We are suckers for flattery. As people like our posts on facebook and we get more followers on twitter, we feel motivated to write and ourselves engage more to receive even more flattery.
Contact
Contact between people who would normally dislike each other can increase likening and understanding between the two, depending on the experience. A positive experience leads to a higher familiarity and liking while a distasteful one produces the opposite effect.
Mass chat communities like those generated by IRC has brought people together that would normally never get a chance to talk. Even though the chat might not have been about breaking down boundaries, meeting and talking to people not similar to ourselves increase our liking of the group those people represent.
Cooperation rather than competition
We like people and things that are familiar to us or seems like us, as we can identify with them. We also have a tendency to dislike people and things that are not familiar and do not seem like us.
Once competition between people starts, this effect is enhanced. Competition makes us stick with what we know and distance ourselves from what we dont.
Cooperation on the other has a dampening effect. Cooperation with people who are not like us can help us like them more. Even a vague understanding of a cooperation taking place will help. Use cooperation to increase liking between groups that a far apart. Point out cooperation in a situation when it exists naturally. Amplify cooperation when it exists only weakly. Try to manufacture it when it is absent. Can you create a feeling of us against the system, that we pull together for mutual benefit, or that you work together with your users to get them to kick ass?
On the other hand, competition can help companies make you dislike their competitors, and make you love their own company more.
Apples Mac vs. PC campaign played on the long-time rivalry and competition between Macs and PCs. It helped start and spark a bond between Mac owners that PC owners never had  a connection with one simple Apple-favored message: PC is bad, Mac is good. Brilliant execution!
Conditioning  association
We have a tendency to try to bask in reflected glory by what and who we associate and connect ourselves with. We try to connect ourselves to success by using the pronoun we and distance ourselves from losers by using they. It works. Connect yourself or your products with things your users like to increase liking.

The specialized instrument microphone company, Applied Microphone Technology spends large amounts of energy and money to endorse famous and respected artists who use their product. This is an attempt let the liking of the endorsed artists fall back on the microphone company because of the association.

---

## Limited Choice

**URL Validation:** https://ui-patterns.com/patterns/Limited-choice

### Problem Summary
We are more likely to make a decision when there are fewer options to choose from

### Solution
How many choices do you offer? Can this be reduced? Every time you make it easier for users to think, they are more likely to make a decision.
Simplify decision paths and present the more complex choices first.

	Reduce choices available. How many choices do you offer? Can this be reduced? Every time you make it easier for users to think, they are more likely to make a decision.
	Find the right amount of choices. At first, more choices lead to more satisfaction, but as number of choices increases, satisfaction peaks whereafter people tend to feel more pressure, confusion, and dissatisfaction with their choice.
	Avoid analysis paralysis. When confronted with too many choices especially under a time constraint, many people prefer to make no choice at all, even if making a choice would lead to a better outcome.

### Rationale
Making a decision becomes overwhelming when we aare faced with many options due to the many potential outcomes and risks that may result from making the wrong choice. Having too many approximately equally good options is mentally draining. Although larger choice sets can be initially appealing, smaller choice sets lead to increased satisfaction and reduced regret.

### Usage Examples
How many choices do you offer? Can this be reduced? Every time you make it easier for users to think, they are more likely to make a decision.
Simplify decision paths and present the more complex choices first.

	Reduce choices available. How many choices do you offer? Can this be reduced? Every time you make it easier for users to think, they are more likely to make a decision.
	Find the right amount of choices. At first, more choices lead to more satisfaction, but as number of choices increases, satisfaction peaks whereafter people tend to feel more pressure, confusion, and dissatisfaction with their choice.
	Avoid analysis paralysis. When confronted with too many choices especially under a time constraint, many people prefer to make no choice at all, even if making a choice would lead to a better outcome.

---

## Limited duration

**URL Validation:** https://ui-patterns.com/patterns/Limited-duration

### Problem Summary
Use time limitations to push users to take action

### Solution
Introduce time-constraints to enforce the feeling of a product, service, or item being scarce. Time-based scarcity invokes a feeling of urgency  that we better hurry up and make our decision to buy or use before the opportunity is over.
The thought of a missed opportunity that we will not be able to obtain at a later time makes us act now. We would rather act now and not miss out on an opportunity  even though we are not totally sure if the decision will be of actual value. Time-based scarcity invoked effectively can make people make a decision that they might not have made if they had better time to evaluate alternatives.

### Rationale
We hate to loose the freedoms we already have. As opportunities become less available we tend to desire them significantly more. We put more value into the freedom of choice, which is why we react to time-based scarcity by making quick and sometimes uninformed decisions. We react against lost freedom of choice by wanting and trying to possess scarce items more than before.

### Usage Examples
Introduce time-constraints to enforce the feeling of a product, service, or item being scarce. Time-based scarcity invokes a feeling of urgency  that we better hurry up and make our decision to buy or use before the opportunity is over.
The thought of a missed opportunity that we will not be able to obtain at a later time makes us act now. We would rather act now and not miss out on an opportunity  even though we are not totally sure if the decision will be of actual value. Time-based scarcity invoked effectively can make people make a decision that they might not have made if they had better time to evaluate alternatives.

---

## Search Filters

**URL Validation:** https://ui-patterns.com/patterns/LiveFilter

### Problem Summary
The users needs to conduct a search using contextual filters that narrow the search results.

### Solution
Refine search results in real time using one or more filters.
Present everything available, and then encourage the user to progressively remove what they do not need by applying one or more filters. With immediate feedback, the experience is used from a monologue to a conversation. Only use this pattern when it helps simplify the search experience.
Present the user with a list filter categories, and let the user filter these by inserting input in text boxes, choosing options in dropdown boxes or even through checkboxes or radiobuttons. Whenever the user makes a change to any of the input fields, the results are automatically updated.

### Rationale
With a search, you start off with nothing and potentially end up with nothing. Counter to this approach is filtering, where we present everything available, and then encourage the user to progressively remove what they do not need1.  Pete Forde

Using the live filter pattern moves the search from a monologue to a conversation. The user can progressively remove what they dont need step by step and receive feedback immediately.
When you weigh your decision to use this filter, consider whether the pattern complicates or simplifies search. If it does anything else than simplify finding the correct search result, choose another solution.

### Usage Examples
Refine search results in real time using one or more filters.
Present everything available, and then encourage the user to progressively remove what they do not need by applying one or more filters. With immediate feedback, the experience is used from a monologue to a conversation. Only use this pattern when it helps simplify the search experience.
Present the user with a list filter categories, and let the user filter these by inserting input in text boxes, choosing options in dropdown boxes or even through checkboxes or radiobuttons. Whenever the user makes a change to any of the input fields, the results are automatically updated.

---

## Preview

**URL Validation:** https://ui-patterns.com/patterns/LivePreview

### Problem Summary
The user wants to check how changes in form fields affect an end result as quickly as possible.

### Solution
Let users preview consequences of an action before committing to it.
Update a preview of what modifying a form will result in throughout the entire interaction with the form. Instead of waiting for the user to submit the form, the changes are shown immediately in a preview. Each user event of significance results in a browser-side processing.

### Rationale
Previews make it easier for users to decide whether or not to commit to a change and thus invite safe exploration and playful creativity. Show feedback immediately in live previews to further spark fun, play, and exploration.
The result is increased interactivity. The user does not need to wait for page reload on a form submit to find out whether data was inputted correctly into the form. The feedback is immediate.

### Usage Examples
Let users preview consequences of an action before committing to it.
Update a preview of what modifying a form will result in throughout the entire interaction with the form. Instead of waiting for the user to submit the form, the changes are shown immediately in a preview. Each user event of significance results in a browser-side processing.

---

## Loss Aversion

**URL Validation:** https://ui-patterns.com/patterns/Loss-aversion

### Problem Summary
Our fear of losing motivates us more than the prospect of gaining something of equal value

### Solution
In the critical moment of making a decision, the users choices can be framed as either a gain or a loss.
The value function explained graphically

### Rationale
The displeasure of losses makes us go to greater lengths to avoid them rather than take risks to obtain gains. Frame gains and losses to make some options seem more desirable than others. What is lost by leaving your service? Offer perceived value that can potentially be lost on closing an account.
When the outcomes of a decision are uncertain, emotions play a role in guiding it. Emotions are the tools we use to simplify the world into heuristics, or general rules of thumb, as they allow our brains to take shortcuts and approximate rational thinking. Fear and anxiety detect risky choices, why we need emotions to make rational decisions.
In some cases however, our emotions guide us beyond what is rational. One such situation is our divergent assessment of risk regarding respectively gains and losses. Kahneman and Tversky found that we are risk aversive in decisions regarding gains and risk seeking in decisions regarding losses; we have a tendency to strongly prefer avoiding losses to acquiring gains.
This means that our willingness to make a decision does not have anything to do with how much we already have (i.e. our state of wealth), but rather if we are to gain or loose. So even if we have a million dollars in our bank account, we will still be as aversive towards loosing $20 as we would if we had no money.
Example: Discounts and trial periods
Preferring avoiding losses to acquiring gains is why discounts and trial periods work. We buy a product with a discount in fear of loosing the opportunity to buy the product at an as low price again. Furthermore, we are more likely to engage in free trial periods than paying up front, as we tell ourselves that a free product does not cost us anything.
The truth however is that we pay with our time and effort in getting used and accustomed to the product so that when the trial period is over the cost of continuing is framed as a loss instead of a gain; we will loose all the time and effort invested in the product if we dont continue.

### Usage Examples
In the critical moment of making a decision, the users choices can be framed as either a gain or a loss.
The value function explained graphically

---

## Module Tabs

**URL Validation:** https://ui-patterns.com/patterns/ModuleTabs

### Problem Summary
Content needs to be separated into sections and accessed via a single content area using a flat navigation structure that does not refresh the page when selected.

### Solution
Present the content of one tab inside a box (content area)
	Place a horizontal bar on top of the content area with links representing tabs
	Refrain from having more than one line of links in the top horizontal tab bar
	Use color coding or other visual support to indicate what tab is currently being viewed
	Present the content of each tab in the same content area
	Only one content area should be visible at a time


	Maintain the same structure of the top horizontal tab bar after a new tab has been clicked
	Only the content area of the tabs and the horizontal tab bar should be changed when a user clicks a new tab
	If possible, the page is not refreshed when a tab is clicked.
	A new page is not loaded when a tab is clicked

### Rationale
The Navigation tabs pattern is an extension of the desktop metaphor in which physical objects are represented as GUI elements. Navigation tabs are derived from the idea of folders in a file-cabinet and are thus familiar to the end user
Module Tabs provide an easy way to show large amounts of similar structured data parted by categories
Tabs create a context for content, when a tab is selected the relevant content is loaded inside the content area.

### Usage Examples
Present the content of one tab inside a box (content area)
	Place a horizontal bar on top of the content area with links representing tabs
	Refrain from having more than one line of links in the top horizontal tab bar
	Use color coding or other visual support to indicate what tab is currently being viewed
	Present the content of each tab in the same content area
	Only one content area should be visible at a time


	Maintain the same structure of the top horizontal tab bar after a new tab has been clicked
	Only the content area of the tabs and the horizontal tab bar should be changed when a user clicks a new tab
	If possible, the page is not refreshed when a tab is clicked.
	A new page is not loaded when a tab is clicked

---

## Navigation Tabs

**URL Validation:** https://ui-patterns.com/patterns/NavigationTabs

### Problem Summary
Content needs to be separated into sections and accessed using a flat navigation structure that gives a clear indication of current location.

### Solution
A horizontal bar contains the different sections or categories of your website.
	Each section or category is represented by a tab that most commonly resembles a button. This is why the whole button should be clickable, and not just the text that labels the section.
	Optionally, a bar below the top bar can contain subsections of the currently selected item in the top bar
	The navigation tab is persistent across all pages that the tabs link to.
	The same structure (order) of the navigation tabs should be maintained from page to page, so that the user can relate the navigation of the different pages to each other.
	The selected tab should be highlighted to indicate current location.
	If subsections are used (a second horizontal bar below the top bar) there should be a clear visual connection between the currently selected top tab and the bar below showing subsections.

### Rationale
The Navigation tabs pattern is an extension of the desktop metaphor in which physical objects are represented as GUI elements. Navigation tabs are derived from the idea of folders in a file-cabinet and are thus familiar to the end user
Navigation tabs provide a clear visual indication of what content can be found on a website and places the current location in context by highlighting it.

### Usage Examples
A horizontal bar contains the different sections or categories of your website.
	Each section or category is represented by a tab that most commonly resembles a button. This is why the whole button should be clickable, and not just the text that labels the section.
	Optionally, a bar below the top bar can contain subsections of the currently selected item in the top bar
	The navigation tab is persistent across all pages that the tabs link to.
	The same structure (order) of the navigation tabs should be maintained from page to page, so that the user can relate the navigation of the different pages to each other.
	The selected tab should be highlighted to indicate current location.
	If subsections are used (a second horizontal bar below the top bar) there should be a clear visual connection between the currently selected top tab and the bar below showing subsections.

---

## Need for Closure

**URL Validation:** https://ui-patterns.com/patterns/Need-for-closure

### Problem Summary
We have a desire for definite cognitive closure as opposed to enduring ambiguity.

### Solution
Motivate your users to act by providing subtle cues to completion. As humans, we have an innate motivation to seek away from ambiguity towards closure. By providing small tasks that plays on our need for closure, you can provide small successes for your users and let them feel as they are working their way out of ambiguity and doubt towards completeness and certainty

	Encourage completion. Encouraging people to strive for completeness by achieving goals or collecting items until they have a full set. The compulsion to collect, to be complete, drives people to action.
	Highlight lacking closure. Highlight unfinished business and provide clear and effortless ways of alleviating the pain to drive action.
	Provide a path toward completion. Make it effortless for users to understand what options needs to be taken to reach a state of completeness.

### Rationale
As humans, we strive toward satisfying our goals and all feel we have a need for fulfilling them. This need for not leaving things be, is a key motivator for acting on our dreams. It is important for us to perceive a movement towards closure.
The tension arising out of the need for closure is called frustration, the closure is called satisfaction2. Once satisfaction has been reached, the imbalance is removed and thus disappears.
The feeling of ambiguity or uncertainty motivate us to find answers. The perceived cost of lacking closure, such as missing deadlines, drives us forward toward action. This makes us freeze on early judgmental cues that in turn introduce biases in our thinking. We like closures to be permanent and will do much to keep them as such. Too much choice will lead to indecision and lower sales.

### Usage Examples
Motivate your users to act by providing subtle cues to completion. As humans, we have an innate motivation to seek away from ambiguity towards closure. By providing small tasks that plays on our need for closure, you can provide small successes for your users and let them feel as they are working their way out of ambiguity and doubt towards completeness and certainty

	Encourage completion. Encouraging people to strive for completeness by achieving goals or collecting items until they have a full set. The compulsion to collect, to be complete, drives people to action.
	Highlight lacking closure. Highlight unfinished business and provide clear and effortless ways of alleviating the pain to drive action.
	Provide a path toward completion. Make it effortless for users to understand what options needs to be taken to reach a state of completeness.

---

## Negativity bias

**URL Validation:** https://ui-patterns.com/patterns/Negativity-bias

### Problem Summary
We have a tendency to pay more attention and give more weight to negative than positive experiences or other kinds of information.

### Solution
Bad is stronger than good. Negative information will attract our attention more than positive information will.
When deciding on what information is presented to users of your system, consider the fact that negative information or design elements with a negative tone will ring more attention than positive information and design will.
You can utilize this fact in your design by paying great attention to what negative feedback is presented to the user. Is it really important? Does it bring the users closer to their goal(s)? If you want users to pay attention to positive information, be careful not to let negative feedback outshine the positive.

	Adjust your frame. Negative messages will outweigh positive ones. Consider separating positive messages from negative ones to harvest the full value of them  or even integrating multiple negative messages into one: get it all out. Be careful not to let negative feedback to users outshine the positive.
	Turn negative messages into positive experiences. If you do need to convey a negative message to your users, consider how you can turn the negative experience into a positive one by immediately providing quick and effortless ways to solve the pain. Give a helpful hand.
	Anticipate bad experiences. Map out the emotional rollercoaster your users are going through in their customer journey and work to find solutions to accommodate users before confusion, lack of information, or misunderstandings becomes a problem.

### Rationale
We pay more attention and give more weight to negative feedback than positive.
As weve seen with loss aversion, we work much harder to avoid losing $100 than we will work to gain the same amount  and painful experiences (loss) are much more memorable than pleasurable ones (gain). But whereas loss aversion refers to negative values, the negativity bias refers to negative information1.
Customers buy less as a reaction to bad news, but not more as a reaction to good news. When of equal intensity, things of a more negative nature (unpleasant thoughts, emotions, or social interactions) have a greater effect on a persons psychological state than neutral or positive things. As humans, we give priority to bad news why only few bad moments can ruin a perfect reputation.

### Usage Examples
Bad is stronger than good. Negative information will attract our attention more than positive information will.
When deciding on what information is presented to users of your system, consider the fact that negative information or design elements with a negative tone will ring more attention than positive information and design will.
You can utilize this fact in your design by paying great attention to what negative feedback is presented to the user. Is it really important? Does it bring the users closer to their goal(s)? If you want users to pay attention to positive information, be careful not to let negative feedback outshine the positive.

	Adjust your frame. Negative messages will outweigh positive ones. Consider separating positive messages from negative ones to harvest the full value of them  or even integrating multiple negative messages into one: get it all out. Be careful not to let negative feedback to users outshine the positive.
	Turn negative messages into positive experiences. If you do need to convey a negative message to your users, consider how you can turn the negative experience into a positive one by immediately providing quick and effortless ways to solve the pain. Give a helpful hand.
	Anticipate bad experiences. Map out the emotional rollercoaster your users are going through in their customer journey and work to find solutions to accommodate users before confusion, lack of information, or misunderstandings becomes a problem.

---

## Pagination

**URL Validation:** https://ui-patterns.com/patterns/Pagination

### Problem Summary
The user needs to view a subset of sorted data in a comprehensible form.

### Solution
Break a complete dataset into smaller sequential parts and provide separate links to each.
Provide pagination control to browse from page to page. Let the user browse to the previous and next pages by providing links to such actions. Also, provide links to the absolute start and end of the dataset (first and last).
If the dataset has a known size then show a link to the last page. If the dataset’s size is variable then do not show a link to the last page.

### Rationale
Reduce perceived complexity by parting large datasets into smaller chunks that are more manageable for the user. Significant technical performance can be achieved by only having to return subsets of the overall data.
First and foremost, pagination parts large datasets into smaller bits that are manageable for the user to read and cope with. Secondly, pagination controls conveys information to the user about, how big the dataset is, and how much is left to read or view and how much have they already viewed.
Pagination provides the user with a natural break from reading or scanning the contents of the dataset, and allows them to re-evaluate whether they wish to continue looking through more data, or navigate away from the page. This is also why pagination controls are most often placed below the list: to provide the user with an option to continue reading through the larger dataset.

### Usage Examples
Break a complete dataset into smaller sequential parts and provide separate links to each.
Provide pagination control to browse from page to page. Let the user browse to the previous and next pages by providing links to such actions. Also, provide links to the absolute start and end of the dataset (first and last).
If the dataset has a known size then show a link to the last page. If the dataset’s size is variable then do not show a link to the last page.

---

## Password Strength Meter

**URL Validation:** https://ui-patterns.com/patterns/PasswordStrengthMeter

### Problem Summary
You want to make sure your users passwords are sufficiently strong in order to prevent malicious attacks.

### Solution
A password’s strength is measured according to predefined rules and is displayed using a horizontal scale next to the input field. If the password is weak then only a small portion of the horizontal bar is highlighted. The greater the strength of the password the more the horizontal bar is highlighted.
The password strength is also appropriately indicated by coloring the bar in a color associative with good or bad: Green indicating a strong password and red indicating a weak password.
How strong a password?
The definition of a strong password can be intensely argued. A forced complex password at first glance only spells increased security, but forcing too complex and rigid rules on password can have the opposite effect. As passwords are forced to be complex, they also become increasingly harder to remember by the user. This occasionally leads to a self-destruction of the increased security, as some users simply write it down on a small sticky note and paste it up on their screen in order to remember their new complex password. This is especially a problem in places with the policy of forced password renewal every 3 months.
What is a strong password?
With the above mentioned in mind, I should stress that a sufficiently strong password does not necessarily need to fulfill all of the rules below, but merely a few will do. Consider the following rules, for each rules followed add a point to the passwords strength level (so that 0 points is the weakest, and 5 is the strongest). UI-patterns.com defines a strong password when it…:

	Has more than 8 characters
	Contains both lowercase and uppercase letters
	Contains at least one numerical character
	Contains special characters
	Has more than 12 characters

This would result in 6 levels of password strength depending on how many of the above mentioned criteria are being met.
Dictionary attacks
While the above mentioned password check can easily be done using only client-side javascript, it does not prevent against dictionary attacks. To ease the memorization of passwords, people tend to use real words as passwords and merely substitute characters with numbers or special characters. An example of such a password could be P@ssw0rd, which really isnt a strong password. Modern password breaking software is fairly good at guessing such number/letter substitutions. To check against such strength, you would need to do ajax calls that would check with your own dictionary if the password was strong or not.
Choosing an appropriate level of password strength
You need to determine the password strength and complexity according to what you want to protect. You need to draw the line somewhere. For 99% of the content out there it can easily be argued that merely the first 2 or 3 rules mentioned above will be sufficient.
General guidelines on choosing a password

	Use a password of a seemingly random selection of letters and numbers
	Use a password that you can type without you having to look at the keyboard (decreases possibility of people stealing your password)
	Change your password regularly
	Do not use your network ID in any form (capitalized, reversed, doubled, etc.)
	Do not use your first, middle or last name or anyone elses in any form.
	Do not use your initials or any nicknames you or somebody else might have.
	Do not use a word contained in any dictionary (English or foreign), spelling list, abbreviation list, etc.
	Do not use information that people can easily obtain about you (license plate, pet name, date of birth, telephone numbers)
	Do not use password of all alphabetical characters or only numeric characters  mix them up.
	Do not use keyboard sequences (for instance qwerty or asdf)

### Rationale
By showing a password strength meter beside the password field, the user is forced to consider using a password with an appropriate strength. By putting a minimum level of password strength you can even use the password strength meter to force a heightened security to your website.
Using a password strength indicator on the website, adds another level of security is added to the site.  This not only makes the current users of the site feel more secure, but potential clients might use this as a requisite when deciding to conduct business with a company.

### Usage Examples
A password’s strength is measured according to predefined rules and is displayed using a horizontal scale next to the input field. If the password is weak then only a small portion of the horizontal bar is highlighted. The greater the strength of the password the more the horizontal bar is highlighted.
The password strength is also appropriately indicated by coloring the bar in a color associative with good or bad: Green indicating a strong password and red indicating a weak password.
How strong a password?
The definition of a strong password can be intensely argued. A forced complex password at first glance only spells increased security, but forcing too complex and rigid rules on password can have the opposite effect. As passwords are forced to be complex, they also become increasingly harder to remember by the user. This occasionally leads to a self-destruction of the increased security, as some users simply write it down on a small sticky note and paste it up on their screen in order to remember their new complex password. This is especially a problem in places with the policy of forced password renewal every 3 months.
What is a strong password?
With the above mentioned in mind, I should stress that a sufficiently strong password does not necessarily need to fulfill all of the rules below, but merely a few will do. Consider the following rules, for each rules followed add a point to the passwords strength level (so that 0 points is the weakest, and 5 is the strongest). UI-patterns.com defines a strong password when it…:

	Has more than 8 characters
	Contains both lowercase and uppercase letters
	Contains at least one numerical character
	Contains special characters
	Has more than 12 characters

This would result in 6 levels of password strength depending on how many of the above mentioned criteria are being met.
Dictionary attacks
While the above mentioned password check can easily be done using only client-side javascript, it does not prevent against dictionary attacks. To ease the memorization of passwords, people tend to use real words as passwords and merely substitute characters with numbers or special characters. An example of such a password could be P@ssw0rd, which really isnt a strong password. Modern password breaking software is fairly good at guessing such number/letter substitutions. To check against such strength, you would need to do ajax calls that would check with your own dictionary if the password was strong or not.
Choosing an appropriate level of password strength
You need to determine the password strength and complexity according to what you want to protect. You need to draw the line somewhere. For 99% of the content out there it can easily be argued that merely the first 2 or 3 rules mentioned above will be sufficient.
General guidelines on choosing a password

	Use a password of a seemingly random selection of letters and numbers
	Use a password that you can type without you having to look at the keyboard (decreases possibility of people stealing your password)
	Change your password regularly
	Do not use your network ID in any form (capitalized, reversed, doubled, etc.)
	Do not use your first, middle or last name or anyone elses in any form.
	Do not use your initials or any nicknames you or somebody else might have.
	Do not use a word contained in any dictionary (English or foreign), spelling list, abbreviation list, etc.
	Do not use information that people can easily obtain about you (license plate, pet name, date of birth, telephone numbers)
	Do not use password of all alphabetical characters or only numeric characters  mix them up.
	Do not use keyboard sequences (for instance qwerty or asdf)

---

## Pattern Recognition

**URL Validation:** https://ui-patterns.com/patterns/Pattern-recognition

### Problem Summary
Even when there is no pattern, we seek ways to organize and simplify complex information

### Solution
We try to make sense of how information is grouped and presented.

	Gamify the experience. Make a game of arranging things in a manner that sparks curiosity and encourages pattern-seeking behavior. Consider playful ways to enable users to organize or label information and make a game of arranging things.
	Provide affordance cues. Give cues as to how the user should interact with your experience. These cues tell you what to do with an object once you see it, such as a “push” or “pull” sign on a door.
	Build a taste profile to reduce cognitive load. As you learn about the userss knowledge, experience, and preference through the choices and action they make, it is possible through machine learning and simple categorization to build a data profile that can predict similar objects of preference. This can in turn help reduce friction as you will be able to present content that matches the preference of the user more accurately.

### Rationale
We seek ways to organize and simplify complex information as we try to make sense of how information is grouped and presented. We look for cues (affordances) in objects to figure out how we should interact with them and use our knowledge and past experience to make sense and meaning.

### Usage Examples
We try to make sense of how information is grouped and presented.

	Gamify the experience. Make a game of arranging things in a manner that sparks curiosity and encourages pattern-seeking behavior. Consider playful ways to enable users to organize or label information and make a game of arranging things.
	Provide affordance cues. Give cues as to how the user should interact with your experience. These cues tell you what to do with an object once you see it, such as a “push” or “pull” sign on a door.
	Build a taste profile to reduce cognitive load. As you learn about the userss knowledge, experience, and preference through the choices and action they make, it is possible through machine learning and simple categorization to build a data profile that can predict similar objects of preference. This can in turn help reduce friction as you will be able to present content that matches the preference of the user more accurately.

---

## Paywall

**URL Validation:** https://ui-patterns.com/patterns/Paywall

### Problem Summary
The user needs to pay to get access to a restricted area on a website.

### Solution
Restrict access to users who have paid.
There are a variety of Paywall strategies found in use today. vary. Some strategies close block all content until payment is made, some lure you in with bait and asks for money after viewing an amount of articles, other websites cherry pick content that’s not free for all. Below is an overview of the main variations.
Strategies

	Paywall: All content is behind one big paywall that surrounds the entire site. Examples are The Times


	Freemium: In the freemium model, some content is free for all and some are behind a pay wall. Examples are The Wallstreet Journal, Berlingske, Aftonbladet


	Taxometer: The first few articles are free to view whereafter the paywall kicks in. Examples are The New York Times, Financial Times


	Time limits: You buy a day, week, month or year pass or access to the archive for a number of days. Examples are The Observer, The Guardian


	Bulk sales: Upsale and sale to companies. Examples are Financial Times and Mediawatch


	Sale by the piece: Purchase of single stories and services. Examples are TÃ¦nk, PeepCode

Payment doesnt have to be monetary
Most paywalls include a monetary exchange, however there are several ways a user can pay to get behind a paywall:

	Monetary exchange: The traditional paywall includes some kind of monetary exchange  it can payment for a single piece of information or by subscription


	Subscription to print media: Instead of buying a subscription to use the website only, require users to own a subscription of the print edition of the media in order to enforce both revenue streams: online and offline.


	Permission: Let your users give you permission to call them up, send them emails, to get your information from facebook, to contact your friends, etc.. Getting permission to build a long term relationship can sometimes be more worth than a simple monetary exchange.


	Lead: You could also let users give their permission for an advertiser or other third party to contact them.


	Time: Let your users take a questionnaire   do you want to know about the profile of your users and their behavior  or could an advertiser or other third party be interested in knowing about your users? You could also let your users watch a video commercial from an advertiser or otherwise grow from their valuable time.


	Social sharing: Let users gain admission to content by first socially sharing a link. Some websites and applications use “pay with tweet” and “pay with like” services.

### Rationale
Paywalls are used as an alternative income source for online media websites, where banner advertising has been the tradition. As users move their habits from print to online, media companies find it harder to base their business on advertising revenue only. Paywalls has been widely introduced to make up for the lost revenue.

### Usage Examples
Restrict access to users who have paid.
There are a variety of Paywall strategies found in use today. vary. Some strategies close block all content until payment is made, some lure you in with bait and asks for money after viewing an amount of articles, other websites cherry pick content that’s not free for all. Below is an overview of the main variations.
Strategies

	Paywall: All content is behind one big paywall that surrounds the entire site. Examples are The Times


	Freemium: In the freemium model, some content is free for all and some are behind a pay wall. Examples are The Wallstreet Journal, Berlingske, Aftonbladet


	Taxometer: The first few articles are free to view whereafter the paywall kicks in. Examples are The New York Times, Financial Times


	Time limits: You buy a day, week, month or year pass or access to the archive for a number of days. Examples are The Observer, The Guardian


	Bulk sales: Upsale and sale to companies. Examples are Financial Times and Mediawatch


	Sale by the piece: Purchase of single stories and services. Examples are TÃ¦nk, PeepCode

Payment doesnt have to be monetary
Most paywalls include a monetary exchange, however there are several ways a user can pay to get behind a paywall:

	Monetary exchange: The traditional paywall includes some kind of monetary exchange  it can payment for a single piece of information or by subscription


	Subscription to print media: Instead of buying a subscription to use the website only, require users to own a subscription of the print edition of the media in order to enforce both revenue streams: online and offline.


	Permission: Let your users give you permission to call them up, send them emails, to get your information from facebook, to contact your friends, etc.. Getting permission to build a long term relationship can sometimes be more worth than a simple monetary exchange.


	Lead: You could also let users give their permission for an advertiser or other third party to contact them.


	Time: Let your users take a questionnaire   do you want to know about the profile of your users and their behavior  or could an advertiser or other third party be interested in knowing about your users? You could also let your users watch a video commercial from an advertiser or otherwise grow from their valuable time.


	Social sharing: Let users gain admission to content by first socially sharing a link. Some websites and applications use “pay with tweet” and “pay with like” services.

---

## Peak-end rule

**URL Validation:** https://ui-patterns.com/patterns/Peakend-rule

### Problem Summary
We primarily judge past experiences on how they were at their peak and how they ended

### Solution
Conduct user research to discover the peaks (good or bad) in the user experience you provide. Do they match what you expected? End points can be obvious (order fulfillment) or subtle (registration confirmation).
Identify and improve.
Designing for the peak-end rule is another way of not focusing on what is less important; about focusing on what brings the most value to the users experience.

	Establish positive peaks and ends. Counteract negative experiences by delivering a clear positive peak- and end-experiences. It can be anything from memorable and enjoyable music, a free sample, a follow-up call, or providing a feeling of success, flow, and accomplishment.
	Map out user emotions. Conduct user research to map out user emotions and how they change over time. Work towards your peaks and ends being positive and accommodate potential negative experiences with positive ones. Use tools like customer journey mapping or empathy mapping to map out user emotions over time to see the full picture. End points can be obvious (order fulfilment) or subtle (registration confirmation). Identify and improve.
	Postpone the end of your experience. Unless your users escapes your experience before time (then the peak and end could be the same), you usually have plenty of opportunities of controlling the end of an experience to ensure it is a positive one. Conduct pro-active after sales care, provide a 30 minute coaching call, or put yourself in a position to learn how you can do better next time.

### Rationale
Pleasant or unpleasant, our brains heavily weigh the the most intense felt point and the end when judging an experience, rather than on its total sum or average of every moment. Other information like duration and other logically relevant information aside from the peak and end is not lost, but merely neglected.
The peak end rule is a heuristic in which we judge our past experiences almost entirely on how they were at their peak (whether pleasant or unpleasant) and how they ended1. When we do this we discard virtually all other information, including net pleasantness or unpleasantness and how long the experience lasted.
We only remember certain details of a whole experience; the peak and the end. Whether most parts of the experience were acceptable is without influence on the users perception of the experience as a whole. An acceptable experience is often neither memorable, nor differentiating and will not be what makes or brakes your product.
Designing for the peak-end rule is about designing for the moments of truth. Moments of truth are where users experience how poor or good your product really is, and hopefully how it will help them kick ass. A sure moment of truth is at the end of an experience, but there are more. Find your products moments of truth through user research and address them. Emphasize them. Turn up the volume of the peak as much as possible and make sure it is pleasant so that it will leave a great lasting impression. Make sure that your peak and end is memorable, branded, satisfactory and different from your competitors.
An interesting twist to the peak-end rule was found when it came to measuring the experienced discomfort of pain. Consider the series 2-5-8 and 2-5-8-4 in which the numbers refer to reports of pain provided on a 10-point scale every 5 minutes. Rationally, adding 5 extra minutes of pain will only increase total discomfort, although experiments showed the longer period of pain (20 minutes), but with a period of diminished discomfort in the end, were rated less discomforting than the shorter period of pain (15 minutes), but with an increased discomfort in the end.
An episode, in which discomfort increases gradually to a high level, is evaluated similarly to an episode in which discomfort is high throughout. Furthermore, when test subjects were asked to evaluate moments, duration was completely neglected until they reminded themselves that it is better for episodes of discomfort to be short rather than long.

### Usage Examples
Conduct user research to discover the peaks (good or bad) in the user experience you provide. Do they match what you expected? End points can be obvious (order fulfillment) or subtle (registration confirmation).
Identify and improve.
Designing for the peak-end rule is another way of not focusing on what is less important; about focusing on what brings the most value to the users experience.

	Establish positive peaks and ends. Counteract negative experiences by delivering a clear positive peak- and end-experiences. It can be anything from memorable and enjoyable music, a free sample, a follow-up call, or providing a feeling of success, flow, and accomplishment.
	Map out user emotions. Conduct user research to map out user emotions and how they change over time. Work towards your peaks and ends being positive and accommodate potential negative experiences with positive ones. Use tools like customer journey mapping or empathy mapping to map out user emotions over time to see the full picture. End points can be obvious (order fulfilment) or subtle (registration confirmation). Identify and improve.
	Postpone the end of your experience. Unless your users escapes your experience before time (then the peak and end could be the same), you usually have plenty of opportunities of controlling the end of an experience to ensure it is a positive one. Conduct pro-active after sales care, provide a 30 minute coaching call, or put yourself in a position to learn how you can do better next time.

---

## Positive Mimicry

**URL Validation:** https://ui-patterns.com/patterns/Positive-mimicry

### Problem Summary
We learn by comparing our behavior with the actions of others

### Solution
While positive mimicry has its advantages, its crucial to be cautious of over-imitation. Excessive or overt mimicry might come off as inauthentic or even creepy to the user, leading to mistrust. Moreover, relying solely on mimicry without considering the broader context or individual user needs can result in a disjointed experience. Its also essential to remember that while mimicry can enhance familiarity, innovation should not be sidelined. Striking a balance between familiar (mimicked) patterns and novel features is key to a products success and user satisfaction.
The principle of positive mimicry, rooted in the human tendency to feel more comfortable with the familiar, can be a powerful tool in product design. By echoing users behaviors, choices, and preferences, designers can create a more intuitive and personalized user experience.
An example is adaptive learning platforms adjustoing the learning content based on a users performance, mimicking the tailored approach of a personal tutor. When a user struggles with certain topics, the system will offer more exercises on that subject, ensuring that the content aligns closely with the learners needs.
Similarly, chatbots that learn from past interactions can offer a more personalized service. Instead of providing generic responses, these chatbots can recall previous interactions, mimicking the continuity of conversation youd expect from human-to-human dialogues. This mirroring not only improves the users experience but also fosters trust and rapport.

	Use your customers own words. Learn what language works best and how to better engage interested prospects.
	Lead the way. Demonstrate and encourage positive interactions and behaviors that users can observe and mimic.
	Highlight good behavior. In social contexts, find and reward people who model good behavior to let the crowd know what normal (or intended) behavior is.

The aim is to create a sense of familiarity without coming across as intrusive. Ethically, its essential to ensure that users are aware of and comfortable with how their data is being used for mimicry. Transparent communication about data usage, along with easy-to-access controls for users to manage their data, are fundamental.
Common mistakes include:

	Overpersonalization. While mimicking user behavior can create a tailored experience, taking it to an extreme might make users feel their privacy is invaded. Its crucial to ensure that mimicry does not become surveillance.
	Assumption Errors. Just because a user behaved a certain way once doesnt mean that behavior is a permanent preference. Relying too heavily on a single data point can lead to incorrect assumptions about user preferences.
	Lack of Transparency. Mimicry, by its nature, involves using data about the user. Not being transparent about how this data is collected, stored, and used can lead to trust issues and potential ethical concerns.
	Over-reliance on Automation. While AI and machine learning can be useful tools for implementing mimicry, its essential to have human oversight. Sometimes, the nuances of human behavior can be misinterpreted by algorithms.

Powerful Pairings
By understanding the synergies between positive mimicry and other persuasive patterns, designers can craft more compelling and user-centric experiences.

	Positive Mimicry + Social Proof. Integrating the power of social validation with mimicry can enhance the persuasiveness of a product. For instance, a fitness app could use positive mimicry by adapting workout routines based on user preferences, while simultaneously highlighting popular workouts among peers (social proof). This combination assures users that not only is the app personalized for them, but its also aligned with whats popular or effective for others.
	Positive Mimicry + Commitment  Consistency. Once users make a small commitment, theyre more likely to act consistently with that decision. If a platform mirrors this initial commitment (e.g., a preference set in the beginning), it reinforces their decision and drives further engagement. An e-commerce site, for example, might mimic a users style preferences set during an initial quiz, consistently highlighting products that align with that style throughout the shopping experience.
	Positive Mimicry + Triggers. By pairing timely prompts (triggers) with positive mimicry, platforms can encourage desired behaviors. A language learning app, for instance, might send reminders (triggers) for lessons based on a users past activity times, mimicking their natural schedule.

### Rationale
We often subconsciously and automatically imitate other peoples behavior. You smile when I smile. Mimic your customers terminologies, reuse search queries in your online dialogues, and showcase actual consumers buying or consuming your product.
The main psychological principle behind Positive Mimicry is the inherent human need for social cohesion and acceptance. When we mimic or are mimicked by others, it creates a sense of belonging, validation, and mutual understanding, fostering positive feelings and smoother interactions. Mimicry often occurring outside our conscious awareness, influences our perceptions, feelings, and actions.
Positive Mimicry is grounded in our evolutionary predisposition to adopt behaviors that have proven advantageous or rewarding for others in our environment. By mimicking such behaviors, individuals often hope to achieve similar positive outcomes or be perceived in a more favorable light. This principle operates both on a conscious and subconscious level, influencing a wide range of decisions and actions. While it can lead to constructive outcomes like learning and cooperation, its essential to recognize the boundaries and ensure its applied authentically and ethically.

### Usage Examples
While positive mimicry has its advantages, its crucial to be cautious of over-imitation. Excessive or overt mimicry might come off as inauthentic or even creepy to the user, leading to mistrust. Moreover, relying solely on mimicry without considering the broader context or individual user needs can result in a disjointed experience. Its also essential to remember that while mimicry can enhance familiarity, innovation should not be sidelined. Striking a balance between familiar (mimicked) patterns and novel features is key to a products success and user satisfaction.
The principle of positive mimicry, rooted in the human tendency to feel more comfortable with the familiar, can be a powerful tool in product design. By echoing users behaviors, choices, and preferences, designers can create a more intuitive and personalized user experience.
An example is adaptive learning platforms adjustoing the learning content based on a users performance, mimicking the tailored approach of a personal tutor. When a user struggles with certain topics, the system will offer more exercises on that subject, ensuring that the content aligns closely with the learners needs.
Similarly, chatbots that learn from past interactions can offer a more personalized service. Instead of providing generic responses, these chatbots can recall previous interactions, mimicking the continuity of conversation youd expect from human-to-human dialogues. This mirroring not only improves the users experience but also fosters trust and rapport.

	Use your customers own words. Learn what language works best and how to better engage interested prospects.
	Lead the way. Demonstrate and encourage positive interactions and behaviors that users can observe and mimic.
	Highlight good behavior. In social contexts, find and reward people who model good behavior to let the crowd know what normal (or intended) behavior is.

The aim is to create a sense of familiarity without coming across as intrusive. Ethically, its essential to ensure that users are aware of and comfortable with how their data is being used for mimicry. Transparent communication about data usage, along with easy-to-access controls for users to manage their data, are fundamental.
Common mistakes include:

	Overpersonalization. While mimicking user behavior can create a tailored experience, taking it to an extreme might make users feel their privacy is invaded. Its crucial to ensure that mimicry does not become surveillance.
	Assumption Errors. Just because a user behaved a certain way once doesnt mean that behavior is a permanent preference. Relying too heavily on a single data point can lead to incorrect assumptions about user preferences.
	Lack of Transparency. Mimicry, by its nature, involves using data about the user. Not being transparent about how this data is collected, stored, and used can lead to trust issues and potential ethical concerns.
	Over-reliance on Automation. While AI and machine learning can be useful tools for implementing mimicry, its essential to have human oversight. Sometimes, the nuances of human behavior can be misinterpreted by algorithms.

Powerful Pairings
By understanding the synergies between positive mimicry and other persuasive patterns, designers can craft more compelling and user-centric experiences.

	Positive Mimicry + Social Proof. Integrating the power of social validation with mimicry can enhance the persuasiveness of a product. For instance, a fitness app could use positive mimicry by adapting workout routines based on user preferences, while simultaneously highlighting popular workouts among peers (social proof). This combination assures users that not only is the app personalized for them, but its also aligned with whats popular or effective for others.
	Positive Mimicry + Commitment  Consistency. Once users make a small commitment, theyre more likely to act consistently with that decision. If a platform mirrors this initial commitment (e.g., a preference set in the beginning), it reinforces their decision and drives further engagement. An e-commerce site, for example, might mimic a users style preferences set during an initial quiz, consistently highlighting products that align with that style throughout the shopping experience.
	Positive Mimicry + Triggers. By pairing timely prompts (triggers) with positive mimicry, platforms can encourage desired behaviors. A language learning app, for instance, might send reminders (triggers) for lessons based on a users past activity times, mimicking their natural schedule.

---

## Privileges

**URL Validation:** https://ui-patterns.com/patterns/Powers

### Problem Summary
Give users a way to reach their goal more quickly than they could before

### Solution
Provide a way for users to earn a set of powers that will allow them to reach their goal more quickly than they could have before. This pattern is often used in combination with Unlocking features
In web design, there are two common roles that are most often rewarded with special powers: The contributor and curator role.
Reward the contributor and curator roles
A contributor is a person who posts stories, uploads images, makes comments, and in general adds content to a website. Contributions are essential for a website to have interesting content, however without filtering for quality content too many poor contributions can flood a website with otherwise good content. This is where the curator comes in.
Curators are the users who make an effort in defining what is quality content and what is not. They vote quality content up, flag content with profanity, and vote poor quality down.
The relationship between the contributors and curators are often intertwined in that users with a proven track record of quality content are immediately promoted more than a rookie user or a user with a poor track record.
Grant roles
Awarding users with specific powers in a community can help provide users with a specific role (moderator, curator, etc.) and thus help give a sense of purpose, place and a sense of belonging in a community.
Instil a sense of self-determination
According to self-determination theory, people are able to become self-determined when their needs for competence, connection, and autonomy are fulfilled. Granting privileges to individuals can provide a path that will allow them to go their own ways, have a place and connection in a community, and grow their competence to interact with as they administer their powers3.
Common powers given to users
There are several ways to empower users. Here is a list of common powers attained:

	Vote comments up or down
	Power vote  a users vote counts double, triple, or quadruple the vote of regular users
	Delete resources  content, comments, posts, images, users
	Create content  power to post specific types of content: polls, quizzes, or other specialized content
	Contributions immediately promoted as quality  no need to wait for other users to vote it up

### Rationale
Becoming more powerful is something that everyone desires in real life. Being giving special powers, no matter in what form, all have in common that they give you a way to reach your goal more quickly than you could before1.
Provide temporary or permanent benefits or extra abilities to let users reach their goal faster.

### Usage Examples
Provide a way for users to earn a set of powers that will allow them to reach their goal more quickly than they could have before. This pattern is often used in combination with Unlocking features
In web design, there are two common roles that are most often rewarded with special powers: The contributor and curator role.
Reward the contributor and curator roles
A contributor is a person who posts stories, uploads images, makes comments, and in general adds content to a website. Contributions are essential for a website to have interesting content, however without filtering for quality content too many poor contributions can flood a website with otherwise good content. This is where the curator comes in.
Curators are the users who make an effort in defining what is quality content and what is not. They vote quality content up, flag content with profanity, and vote poor quality down.
The relationship between the contributors and curators are often intertwined in that users with a proven track record of quality content are immediately promoted more than a rookie user or a user with a poor track record.
Grant roles
Awarding users with specific powers in a community can help provide users with a specific role (moderator, curator, etc.) and thus help give a sense of purpose, place and a sense of belonging in a community.
Instil a sense of self-determination
According to self-determination theory, people are able to become self-determined when their needs for competence, connection, and autonomy are fulfilled. Granting privileges to individuals can provide a path that will allow them to go their own ways, have a place and connection in a community, and grow their competence to interact with as they administer their powers3.
Common powers given to users
There are several ways to empower users. Here is a list of common powers attained:

	Vote comments up or down
	Power vote  a users vote counts double, triple, or quadruple the vote of regular users
	Delete resources  content, comments, posts, images, users
	Create content  power to post specific types of content: polls, quizzes, or other specialized content
	Contributions immediately promoted as quality  no need to wait for other users to vote it up

---

## Praise

**URL Validation:** https://ui-patterns.com/patterns/Praise

### Problem Summary
Use explicit statements, graphics, a sound effect, or similar indicator to reward a job well done.

### Solution
Praise is a form of feedback that fall into the category of rewards. The opposite of praise if blame or derogation. Where blame or derogation are tools for negative feedback, praise is a positive feedback form.
Consider every moment in the experience you have created for your users and ask yourself the following questions for every one of them in order to figure out if praise is right for just that moment:

	What do users need to know at the moment
	What do users want to know at this moment
	Will the feeling you want your users to feel be enforced by praise at this moment?
	What do the users want to feel in this moment? Is there an opportunity to use praise to create a situation where they can feel that?
	Can praise be used to enforce the correct behavior?
	What are your users goal at this moment? Will praise help them toward this goal?

Praise is interpreted simply by users: the system has judged you, and it approves.

### Rationale
Guide your users toward your preferred behavior by praising it when it is conducted.

### Usage Examples
Praise is a form of feedback that fall into the category of rewards. The opposite of praise if blame or derogation. Where blame or derogation are tools for negative feedback, praise is a positive feedback form.
Consider every moment in the experience you have created for your users and ask yourself the following questions for every one of them in order to figure out if praise is right for just that moment:

	What do users need to know at the moment
	What do users want to know at this moment
	Will the feeling you want your users to feel be enforced by praise at this moment?
	What do the users want to feel in this moment? Is there an opportunity to use praise to create a situation where they can feel that?
	Can praise be used to enforce the correct behavior?
	What are your users goal at this moment? Will praise help them toward this goal?

Praise is interpreted simply by users: the system has judged you, and it approves.

---

## Pricing table

**URL Validation:** https://ui-patterns.com/patterns/PricingTable

### Problem Summary
The user needs to get an overview of what pricing plans are offered and how they differ

### Solution
Pricing tables are used as a way to illustrate how features of a product differ as the price changes.
Display the different version of a product in a table aligning price and features for comparison.
A list of the most frequently asked questions (FAQ) regarding the product is often listed directly below the pricing table. These often address issues that potential customers typically worry about: how does the free plan work, is there a money-back-guarantee, how will I be billed, etc.
It is a very common part of Application Service Providers (ASPs) marketing websites. In the most cases, these only have one major product to offer, but offers this product in different variants (plans). On these kind of websites, the price is most often based on a monthly/quarterly/yearly subscription plan.
When you create your pricing table, it is good to consider the following points:

	Visually separate plans by using alternating background colors. When used sparingly, you can attract attention the plan you want the user to buy.
	Utilize different font sizes and colors for elements you want to stand out: titles, prices, headlines, etc.
	Be aware that users scroll down long tables. Prices at the top of a table might not be visible when theyve reached the bottom. One solution is to place prices both at the top and bottom  another is to keep the pricing table short.

### Rationale
Converting interested visitors into paying customers is your biggest aim. Use pricing tables to illustrate what your product is capable of in full bloom and at the same time to lure them in.

### Usage Examples
Pricing tables are used as a way to illustrate how features of a product differ as the price changes.
Display the different version of a product in a table aligning price and features for comparison.
A list of the most frequently asked questions (FAQ) regarding the product is often listed directly below the pricing table. These often address issues that potential customers typically worry about: how does the free plan work, is there a money-back-guarantee, how will I be billed, etc.
It is a very common part of Application Service Providers (ASPs) marketing websites. In the most cases, these only have one major product to offer, but offers this product in different variants (plans). On these kind of websites, the price is most often based on a monthly/quarterly/yearly subscription plan.
When you create your pricing table, it is good to consider the following points:

	Visually separate plans by using alternating background colors. When used sparingly, you can attract attention the plan you want the user to buy.
	Utilize different font sizes and colors for elements you want to stand out: titles, prices, headlines, etc.
	Be aware that users scroll down long tables. Prices at the top of a table might not be visible when theyve reached the bottom. One solution is to place prices both at the top and bottom  another is to keep the pricing table short.

---

## Product page

**URL Validation:** https://ui-patterns.com/patterns/ProductPage

### Problem Summary
The user need to know details about a product in order to make a purchase decision or satisfy a need for support.

### Solution
Present a given product and group related information into chunks. Optionally provide links to other relevant products.
Product pages usually have the following four design elements:

	Product title (product name)
	Main picture of product
	Price
	Add to cart, Place order or Buy button

Furthermore, the following elements are used when they make sense:

	Sales price (often in red and with original price crossed out)
	Detail images
	Product variants (size, color, etc.)
	Product variant pictures (especially regarding color or different patterns)
	Availability (amount in stock)
	Delivery time
	Quantity input form
	Add to wishlist/Favorite button
	Zoom function
	Short description
	Longer description
	Product specifications/details
	Label (Bestseller, Only few left, Recycled materials,  etc.)
	SKU (Stock Keeping Unit) or other form of product id.
	Special offers (Buy this product + another for $xxx,buy 2 for less, etc.)
	Support info  often with phone number or support email address
	Customize button
	Share on social media buttons (Facebook, Digg, StumbleUpon, etc.)

### Rationale
Converting interested visitors into paying customers is your biggest aim. Design your product pages with the purpose of persuading users to buy one or more of the products you are selling.

### Usage Examples
Present a given product and group related information into chunks. Optionally provide links to other relevant products.
Product pages usually have the following four design elements:

	Product title (product name)
	Main picture of product
	Price
	Add to cart, Place order or Buy button

Furthermore, the following elements are used when they make sense:

	Sales price (often in red and with original price crossed out)
	Detail images
	Product variants (size, color, etc.)
	Product variant pictures (especially regarding color or different patterns)
	Availability (amount in stock)
	Delivery time
	Quantity input form
	Add to wishlist/Favorite button
	Zoom function
	Short description
	Longer description
	Product specifications/details
	Label (Bestseller, Only few left, Recycled materials,  etc.)
	SKU (Stock Keeping Unit) or other form of product id.
	Special offers (Buy this product + another for $xxx,buy 2 for less, etc.)
	Support info  often with phone number or support email address
	Customize button
	Share on social media buttons (Facebook, Digg, StumbleUpon, etc.)

---

## Progressive Disclosure

**URL Validation:** https://ui-patterns.com/patterns/ProgressiveDisclosure

### Problem Summary
The user wants to focus on the task at hand with as few distractions as possible while still being able to dig deeper in details if necessary

### Solution
Present only the minimum data required for the task at hand.
Move complex and less frequently used options out of the main interface. Reveal only essential information and help manage complexity by disclosing information and options progressively.
Examples of Progressive Disclosure are plentiful. A simple Show more link, revealing more information about something, is one of the simplest forms of Progressive Disclosure.

### Rationale
Maintain the focus and attention of users by reducing clutter, confusion, and cognitive workload. Ramp up the experience, moving from simple to complex, from abstract to specific. Progressive Disclosure defers advanced or rarely used features to a secondary screen, reducing cognitive load on the current task at hand. This will help making your application easier to learn and less error-prone due to fewer distractions.
By showing only the information or features relevant to the user’s current activity and delaying other information until it is requested, the user can focus on the main task at hand. By hiding more complex or infrequently used, the interface is de-cluttered; by revealing them only as they are needed, you help users perform a complex, multi-step process on a single page2.
You want to show only essential information in the first step, but still invite to take the next. When a user completes a step, reveal information needed for the next step, keeping all previous steps visible. By keeping previous steps visible, you allow users to change what has been entered. Like in a Wizard, data entered in the current step can affect the behavior of the next.

### Usage Examples
Present only the minimum data required for the task at hand.
Move complex and less frequently used options out of the main interface. Reveal only essential information and help manage complexity by disclosing information and options progressively.
Examples of Progressive Disclosure are plentiful. A simple Show more link, revealing more information about something, is one of the simplest forms of Progressive Disclosure.

---

## Prolonged Play

**URL Validation:** https://ui-patterns.com/patterns/Prolonged-play

### Problem Summary
Reward users by prolonging their game time to allow for higher scores and measures of success

### Solution
Identify the central resource of your system. Odds are that the most valuable reward a user can receive is this. Can you get users to invite, refer, or do good deeds by extending the number of actions permitted by month, total storage space, or number of projects available?
Lurk users to perform a certain action with a motivational carrot. Define and set up goals that are easy to accomplish for users and communicate them well. Once users reach the goal(s) you have set up, reward them with some sort of resource that will prolong their play.
In many games, the goal is to risk your resources in order to gain points. In pinball, you risk your ball, and in Pac-Man you risk your lives. In games with this structure of lives, the most valuable reward a player can get is an extra life. In other games with time constraints, adding extra time is a prolonged game reward1.
In games, prolonged play allows for a higher score and a measure of success1. In web applications, it can motivate engagement, invitations, quality, or whatever behavior you like.
Lets sum it up:

	Identify your central resources. Odds are that the most valuable reward a user can receive is the resource your product is built on. If your product provides cloud storage, then you can prolong play by doling out bonus storage space.
	Use prolonged play as a carrot. Can you get users to invite, refer, or do good deeds by extending the number of actions permitted by month, total storage space, or number of projects available?
	Balance your rewards. Prolonged play is just one type of reward. Generally, the more you can balance the types of the rewards you implement the better. Consider rewarding users with powers, completion, or by unlocking features among others.

Examples
Dropbox.com, a virtual drive for your computer in the sky, will add 250 MB to your account for every person you invite who sign up for their service. As you are set up with a fixed space-limit on your drive, 250 MB is a valuable resource to be rewarded with. It prolongs your play by making it possible for you to store more stuff on your dropbox drive.
forrst.com, a feedback-community of developers and designers, has a concept called Acorns, which you can use to promote your posts. When you sign up, you receive 1 free acorn to let you experience how it is to have a post promoted. You can prolong your acorn play by either buying new ones or earning new ones for good deeds in the forrst.com community.

### Rationale
For products based on resources, such as time, storage, and seats, topping up those resources can be an effective reward to motivate users toward action. Prolonged play is desirable as it allows for a higher measure of success, but it also taps into our natural human drive for survival.

### Usage Examples
Identify the central resource of your system. Odds are that the most valuable reward a user can receive is this. Can you get users to invite, refer, or do good deeds by extending the number of actions permitted by month, total storage space, or number of projects available?
Lurk users to perform a certain action with a motivational carrot. Define and set up goals that are easy to accomplish for users and communicate them well. Once users reach the goal(s) you have set up, reward them with some sort of resource that will prolong their play.
In many games, the goal is to risk your resources in order to gain points. In pinball, you risk your ball, and in Pac-Man you risk your lives. In games with this structure of lives, the most valuable reward a player can get is an extra life. In other games with time constraints, adding extra time is a prolonged game reward1.
In games, prolonged play allows for a higher score and a measure of success1. In web applications, it can motivate engagement, invitations, quality, or whatever behavior you like.
Lets sum it up:

	Identify your central resources. Odds are that the most valuable reward a user can receive is the resource your product is built on. If your product provides cloud storage, then you can prolong play by doling out bonus storage space.
	Use prolonged play as a carrot. Can you get users to invite, refer, or do good deeds by extending the number of actions permitted by month, total storage space, or number of projects available?
	Balance your rewards. Prolonged play is just one type of reward. Generally, the more you can balance the types of the rewards you implement the better. Consider rewarding users with powers, completion, or by unlocking features among others.

Examples
Dropbox.com, a virtual drive for your computer in the sky, will add 250 MB to your account for every person you invite who sign up for their service. As you are set up with a fixed space-limit on your drive, 250 MB is a valuable resource to be rewarded with. It prolongs your play by making it possible for you to store more stuff on your dropbox drive.
forrst.com, a feedback-community of developers and designers, has a concept called Acorns, which you can use to promote your posts. When you sign up, you receive 1 free acorn to let you experience how it is to have a post promoted. You can prolong your acorn play by either buying new ones or earning new ones for good deeds in the forrst.com community.

---

## Rate Content

**URL Validation:** https://ui-patterns.com/patterns/RateContent

### Problem Summary
The user wants to promote a specific piece of content in order to democratically help decide what content is of higher quality.

### Solution
Let users rate content in order to democratically help decide what is of higher quality.
User ratings act as a mechanism to handle risk for your users: is something worthwhile to spend time or money on? Promote community participation by letting users democratically decide what is of higher quality. Consider accompanying quantitative ratings with qualitative comments or reviews.
This pattern is much like the Vote To Promote pattern. It differs from the Vote To Promote pattern by having different outcome. The outcome is to allow users to guide other users about what is good and bad rather than to promote what is interesting.
The pattern consists of a number of mechanisms that work together:

	Voting mechanism. Provide a mechanism for your users to rate an item on a numeric scale. The most popular scale is 1-5, where a rating of one is worse than a rating of 5. A user gets one vote and can possibly add an explanatory comment along with the rating. When a user rates an item, feedback should be given back to the user informing them  that the rating has been recorded.
	Display the average rating an item has received. The average of all ratings an item has received shows the perceived quality of an item, and will guide new users in whether an item is worthwhile.
	Display explanatory comments from users rating an item. An item can often be rated either low or high for a number of different reasons all originating from different users subjective opinion. A perceived flaw by one user is not necessarily a perceived flaw of another. To add a more quality and depth to the given ratings, allow the users to review an item by letting them explain themselves in free text.
	Show the highest rated items. Sum up the highest rated items in lists on a main page.
	Favor quality items. Favor items rated high in search results, when browsing tags, and showing related information.
	Related items. When showing one item, display its rating. Additionally, use the people who also rated the item highly, to create a list of related items, by showing other similar items these people rated highly.

### Rationale
The Rate Content pattern promotes community participation and can assist you in separating good quality content from bad quality content. This is especially useful when your website relies on user submitted content.
Rating content is about handling risk from the users point of view. Will a user on eBay cheat me or is a book on amazon worthwhile my time and money?

### Usage Examples
Let users rate content in order to democratically help decide what is of higher quality.
User ratings act as a mechanism to handle risk for your users: is something worthwhile to spend time or money on? Promote community participation by letting users democratically decide what is of higher quality. Consider accompanying quantitative ratings with qualitative comments or reviews.
This pattern is much like the Vote To Promote pattern. It differs from the Vote To Promote pattern by having different outcome. The outcome is to allow users to guide other users about what is good and bad rather than to promote what is interesting.
The pattern consists of a number of mechanisms that work together:

	Voting mechanism. Provide a mechanism for your users to rate an item on a numeric scale. The most popular scale is 1-5, where a rating of one is worse than a rating of 5. A user gets one vote and can possibly add an explanatory comment along with the rating. When a user rates an item, feedback should be given back to the user informing them  that the rating has been recorded.
	Display the average rating an item has received. The average of all ratings an item has received shows the perceived quality of an item, and will guide new users in whether an item is worthwhile.
	Display explanatory comments from users rating an item. An item can often be rated either low or high for a number of different reasons all originating from different users subjective opinion. A perceived flaw by one user is not necessarily a perceived flaw of another. To add a more quality and depth to the given ratings, allow the users to review an item by letting them explain themselves in free text.
	Show the highest rated items. Sum up the highest rated items in lists on a main page.
	Favor quality items. Favor items rated high in search results, when browsing tags, and showing related information.
	Related items. When showing one item, display its rating. Additionally, use the people who also rated the item highly, to create a list of related items, by showing other similar items these people rated highly.

---

## Reciprocation

**URL Validation:** https://ui-patterns.com/patterns/Reciprocation

### Problem Summary
We feel obliged to give when we receive

### Solution
Make users feel they have been done a favor by the system or other users in order to make them feel obliged to return it. The favor can be annything from receiving a physical gift to a hug  or even a like on facebook. The receiver of the gesture or favor then has the social obligation to respond, following the norm of reciprocity.
Reciprocity can also play out in a negative way: revenge. Even though revenge is a negative behavior, it has been utilized in a number of online games, where you try to get each other. On Foursquare, you can take over the mayorships of other people, which in turn feel obliqued to return the negative favor.
Provoke users to retaliate based on their social obligation to respond.

### Rationale
If we feel we have been done a favor, we will want to return it. When we receive a gift, we are more likely to comply with the demand that follows: we say yes to those we owe.
Reciprocation is part of the norms that form our social behavior. We are raised that returning a favor is the right thing to do and that we should feel bad if we do not return a favor. Our bad conscience will at some point gather up unreturned favors into some sort or action from users.

### Usage Examples
Make users feel they have been done a favor by the system or other users in order to make them feel obliged to return it. The favor can be annything from receiving a physical gift to a hug  or even a like on facebook. The receiver of the gesture or favor then has the social obligation to respond, following the norm of reciprocity.
Reciprocity can also play out in a negative way: revenge. Even though revenge is a negative behavior, it has been utilized in a number of online games, where you try to get each other. On Foursquare, you can take over the mayorships of other people, which in turn feel obliqued to return the negative favor.
Provoke users to retaliate based on their social obligation to respond.

---

## Recognition over Recall

**URL Validation:** https://ui-patterns.com/patterns/Recognition-over-recall

### Problem Summary
We are better at recognizing things previously experienced than we are at recalling them from memory

### Solution
Instead of asking users to recall data from their memory, present a list of items which each represent a certain category of data. Instead of asking users to list things from memory, try complementing or replacing empty form fields with defined, random, and intelligent choices to choose or rate. Use visual imagery, auto-complete, and multiple-choice options.
If youre interested in asking people to list things from memory, consider complementing  or replacing  empty form fields with defined, intelligent, or random choices that people can click on  or rate.
A classic move from using recall memory to recognition memory in user interface design was when modern GUIs (Graphical User Interfaces) slowly began replacing the older command-line interfaces known from DOS or the UNIX prompt. The effort associated with learning commands in the command-line interface made computers difficult to use. By presenting commands in menus in modern GUIs, the recalling commands from memory became obsolete and simplified the ease of use of computers.
Minimize need to recall
Minimize the need to recall information from memory whenever possible. Use easily accessible menus, multiple choice options, auto-complete suggestions, or visual imagery to aid decisions.

### Rationale
Recognition is triggered by context. Weâ€™re quite good at it. With the radio on, we can sing the lyrics to thousands of songs.
Recall works without context. At this, weâ€™re terribly bad. With the radio off, our memories inevitably fade to black.
This imbalance is shared across our senses, and itâ€™s a huge factor in design3.
Recognition vs Recall
Its easier to click and choose from a variety of options than to write out those same things from memory. Recognition tasks provide memory cues that facilitate searching through memory why it is easier to recognize things than recall them from memory. Its easier to provide a correct answer for a multiple-choice question than it is for a fill-in-the-blank question as the multiple-choice questions provide a list of possible answers1. Open-ended short answer questions provide no such memory cues, why the range of possibilities is much greater.
Recognition doesnt involve origin, context, or relevance
Recognition memory is much easier to access than recall memory. While recognition memory is obtained through exposure, recall memory is obtained through learning. Recognition does not necessarily involve memory about origin, context, or relevance while recall  usually involves some combination of of memorization, practice and application. Furthermore recognition memory is retained for longer periods of time than recall memory  it is harder to recall the name of an acquaintance than it is to recognize it when heard1.

### Usage Examples
Instead of asking users to recall data from their memory, present a list of items which each represent a certain category of data. Instead of asking users to list things from memory, try complementing or replacing empty form fields with defined, random, and intelligent choices to choose or rate. Use visual imagery, auto-complete, and multiple-choice options.
If youre interested in asking people to list things from memory, consider complementing  or replacing  empty form fields with defined, intelligent, or random choices that people can click on  or rate.
A classic move from using recall memory to recognition memory in user interface design was when modern GUIs (Graphical User Interfaces) slowly began replacing the older command-line interfaces known from DOS or the UNIX prompt. The effort associated with learning commands in the command-line interface made computers difficult to use. By presenting commands in menus in modern GUIs, the recalling commands from memory became obsolete and simplified the ease of use of computers.
Minimize need to recall
Minimize the need to recall information from memory whenever possible. Use easily accessible menus, multiple choice options, auto-complete suggestions, or visual imagery to aid decisions.

---

## Reduction

**URL Validation:** https://ui-patterns.com/patterns/Reduction

### Problem Summary
Reduce complex behavior to simple tasks, increasing the benefit/cost ratio and in turn influencing users to perform

### Solution
Reduce otherwise complex functionality into something simple and easily understood. The process of hiding complexity implies removing possible areas of use in order to highlight others. Keep it simple. Make it easy. We prefer to use products and services that give us better return on the information we give them.
Reduction happens when the designer make informed and qualified guesses as to what users preferences are. Making design decisions that restrict a products usage to simple and few forms gives a product a direction. A direction that limits what a product can be used for.
The principle of reduction is about hiding complexity  making something very complex seem very simple. The process of hiding complexity implies removing possible areas of use in order to highlight others.
Keep it simple, make it easy.
Reduction implied to navigation.
A wide navigation structure with fewer levels performs better than a narrow navigation structure with more levels.
Reduction based on what other users did
A common way of implementing the principle of reduction, is for a system to make decisions on behalf of the user based on what other users in similar situations decided.
Amazon reduces the task of finding an interesting book to buy to something simple by suggesting books that users with similar interests found interesting.
Google reduces meaningful search on the web to something simple by relying on what was highlighted by other websites via backlinks as being the most relevant for the user.

	Hide complexity. Simplify activities into something simple and easily understood. The process of hiding complexity can imply removing possible areas of use in order to highlight others. Keep it simple. Make it easy.
	Increase benefit/cost ratio. When benefits outweigh friction, the more likely it is that a behavior will be performed.
	Apply good defaults. Reducing complex behavior into something more simple can imply providing fewer choices up front for the users. Make informed decisions based on the nature of their visit or what the majority of similar peers would decide. This will allow you to present a valuable result up front that can later be fine-tuned with more details.

### Rationale
We prefer to use products and services that give us better return on the information we give them.
As humans, we are cognitively lazy. We like to get the maximum benefit for minimum return. We prefer to use products and services that give us better return on the information we give it.
Reduce otherwise complex activities to a few simple steps (or ideally a single step). By making a behavior easier to perform, the ratio between benefit and cost will increase and motivate people to engage in the behavior more frequently. Additionally, simplifying a behavior or activity may increase users self-efficacy (belief in own ability), to perform a specific behavior, which in turn can help develop more positive attitudes toward the behavior, get people to try harder to adopt the behavior, and perform it more frequently.

### Usage Examples
Reduce otherwise complex functionality into something simple and easily understood. The process of hiding complexity implies removing possible areas of use in order to highlight others. Keep it simple. Make it easy. We prefer to use products and services that give us better return on the information we give them.
Reduction happens when the designer make informed and qualified guesses as to what users preferences are. Making design decisions that restrict a products usage to simple and few forms gives a product a direction. A direction that limits what a product can be used for.
The principle of reduction is about hiding complexity  making something very complex seem very simple. The process of hiding complexity implies removing possible areas of use in order to highlight others.
Keep it simple, make it easy.
Reduction implied to navigation.
A wide navigation structure with fewer levels performs better than a narrow navigation structure with more levels.
Reduction based on what other users did
A common way of implementing the principle of reduction, is for a system to make decisions on behalf of the user based on what other users in similar situations decided.
Amazon reduces the task of finding an interesting book to buy to something simple by suggesting books that users with similar interests found interesting.
Google reduces meaningful search on the web to something simple by relying on what was highlighted by other websites via backlinks as being the most relevant for the user.

	Hide complexity. Simplify activities into something simple and easily understood. The process of hiding complexity can imply removing possible areas of use in order to highlight others. Keep it simple. Make it easy.
	Increase benefit/cost ratio. When benefits outweigh friction, the more likely it is that a behavior will be performed.
	Apply good defaults. Reducing complex behavior into something more simple can imply providing fewer choices up front for the users. Make informed decisions based on the nature of their visit or what the majority of similar peers would decide. This will allow you to present a valuable result up front that can later be fine-tuned with more details.

---

## Role Playing

**URL Validation:** https://ui-patterns.com/patterns/Roleplaying

### Problem Summary
People act according to their persona

### Solution
You can put the power of role playing to use in several ways, each with different objectives:

	Set clear community norms. Construct communities and contexts with norms allowing users to play a role their real-world persona would not allow.
	A role to play. What happens if your system gives users a particular role to play or makes them feel like they are playing a role? Playing the role of an advocate of a given position may facilitate opinion change by prompting attention or retention of arguments supporting that position. Once a role has been accepted, the subject is often motivated to seek arguments to support the assigned position.
	Alleviate dissonance. Accepting a role-played position can help reduce cognitive dissonance produced by opposing views.

### Rationale
How we act depends on the social norms and constructs of a context we are in. Role-playing allows us to understand situations not familiar to us by stepping in the shoes of others. Arguments perceived as self-originated may be more readily accepted than ones perceived as having originated externally.

### Usage Examples
You can put the power of role playing to use in several ways, each with different objectives:

	Set clear community norms. Construct communities and contexts with norms allowing users to play a role their real-world persona would not allow.
	A role to play. What happens if your system gives users a particular role to play or makes them feel like they are playing a role? Playing the role of an advocate of a given position may facilitate opinion change by prompting attention or retention of arguments supporting that position. Once a role has been accepted, the subject is often motivated to seek arguments to support the assigned position.
	Alleviate dissonance. Accepting a role-played position can help reduce cognitive dissonance produced by opposing views.

---

## Scarcity

**URL Validation:** https://ui-patterns.com/patterns/Scarcity

### Problem Summary
If something is promoted as being scarce, we perceive it as more desirable and more valuable

### Solution
Scarcity can be effective in several ways.
Time-based scarcity
Time based scarcity is a well used tactic in the retail world. Think of holiday sales, coupons that run out at the end of the month, and for a limited time only-offers. Time can be used to convey scarcity just as stock scarcity can.
Especially web shops try to invoke stock scarcity effects when they tell us that only limited amounts of an item are available. Time-based scarcity invokes a feeling of urgency. We better hurry up and make our purchase before the item is all sold out. This in turn leads to a decision that we might not have made if we had better time to evaluate alternatives.
Stock scarcity
Google used stock scarcity well when they launched their web mail application, Gmail, in private beta. Due to technical constraints, they could not open op for 2 gigabyte storage for everyone (10 megabyte was the norm back then), why they had roll out the service slowly through invitations. This turned out to do Gmail well. The scarcity effect was in full bloom. If you were lucky enough to become a member, you could invite 2 or 3 friends yourself. The service spread fast virally with help of its scarcity and recommendation system.
Restrictions on information (or merely scarce)
We have a tendency to want what has been banned and therefore to presume that is is more worthwhile. We typically react to attempts to censor or otherwise constrain our access to information. We desire and favor banned information more after it has been banned than before the ban.
This type of scarcity even works beyond bans. We will basically find a piece of information more persuasive if we think we cant get it elsewhere.

### Rationale
Scarcity is often used to encourage purchasing behaviors. It prevents customers from taking the time to think and instead pushes them into making a decision immediately. Limit resources, durations, or intervals to make users value an asset more (whether it is a potential purchase or an action which they can carry out).
Scarcity is the condition where there is an inadequate amount of something to please everybody. The feeling of a shortage can be invoked simply by indicating that there is not enough for everybody. If something is scarce, it will seem more desirable and more valuable to us.
According to Cialdini1, the influence scarcity has on us comes from two things: (1) our weakness for shortcuts and the fact that (2) we hate to loose the freedoms we already have.
Our weakness for shortcuts
When things are difficult to possess we typically connect it to being better than those that re easy to possess. We use an items availability to quickly determine its quality and value. By following the scarcity principle we usually and efficiently make correct and quick decisions.
We hate to loose the freedoms we already have
As opportunities become less available, the need to retain those opportunities make us  desire them significantly more. As we loose freedom and choice, we put more value in the them. Because we hate to loose the freedoms we already have, we react by making quick decisions. We react against interferences of removing access to items by wanting and trying to possess the item more than before.

### Usage Examples
Scarcity can be effective in several ways.
Time-based scarcity
Time based scarcity is a well used tactic in the retail world. Think of holiday sales, coupons that run out at the end of the month, and for a limited time only-offers. Time can be used to convey scarcity just as stock scarcity can.
Especially web shops try to invoke stock scarcity effects when they tell us that only limited amounts of an item are available. Time-based scarcity invokes a feeling of urgency. We better hurry up and make our purchase before the item is all sold out. This in turn leads to a decision that we might not have made if we had better time to evaluate alternatives.
Stock scarcity
Google used stock scarcity well when they launched their web mail application, Gmail, in private beta. Due to technical constraints, they could not open op for 2 gigabyte storage for everyone (10 megabyte was the norm back then), why they had roll out the service slowly through invitations. This turned out to do Gmail well. The scarcity effect was in full bloom. If you were lucky enough to become a member, you could invite 2 or 3 friends yourself. The service spread fast virally with help of its scarcity and recommendation system.
Restrictions on information (or merely scarce)
We have a tendency to want what has been banned and therefore to presume that is is more worthwhile. We typically react to attempts to censor or otherwise constrain our access to information. We desire and favor banned information more after it has been banned than before the ban.
This type of scarcity even works beyond bans. We will basically find a piece of information more persuasive if we think we cant get it elsewhere.

---

## Self-Expression

**URL Validation:** https://ui-patterns.com/patterns/Self-expression

### Problem Summary
We seek opportunities to express our personality, feelings, or ideas

### Solution
Find ways for users to express themselves. Allowing customization, posting content, commenting, following, sharing, and using emoticons are all ways that enable self-expression. Feedback mechanisms such as comments or likes can work as great rewards for efforts of self-expression.
The psychological drive to create artifacts that express identity, opinions, and affiliations is not new2. Give people  a way to express themselves, tapping into the fundamental human motivational drive of self-expression.

	Allow customization. Find ways for users to add a personal touch to build deeper and longer-lasting engagements. Allow customization, posting content, commenting, following, sharing, using emoticons, etc. to enable self-expression and let users build a stronger relationship to your product.
	Establish feedback loops. Let users gauge how others judge their self-expression by creating feedback mechanisms such as comments or likes can work as great reward hooks for efforts of self-expression. Consider keeping feedback mechanisms positive and constructive to spark the motivational momentum of the user.
	Create a stage. Look for ways to surface and celebrate unique customizations or personal artefacts by providing users with a stage to express themselves to the broader public.

### Rationale
As humans we are social beings who will always use personal expression to make sense of the world and provide meaning.
Allowing users to customize a product makes it unique and personal to the individual, effectively increasing its perceived and symbolic value to both the creator and to others.

### Usage Examples
Find ways for users to express themselves. Allowing customization, posting content, commenting, following, sharing, and using emoticons are all ways that enable self-expression. Feedback mechanisms such as comments or likes can work as great rewards for efforts of self-expression.
The psychological drive to create artifacts that express identity, opinions, and affiliations is not new2. Give people  a way to express themselves, tapping into the fundamental human motivational drive of self-expression.

	Allow customization. Find ways for users to add a personal touch to build deeper and longer-lasting engagements. Allow customization, posting content, commenting, following, sharing, using emoticons, etc. to enable self-expression and let users build a stronger relationship to your product.
	Establish feedback loops. Let users gauge how others judge their self-expression by creating feedback mechanisms such as comments or likes can work as great reward hooks for efforts of self-expression. Consider keeping feedback mechanisms positive and constructive to spark the motivational momentum of the user.
	Create a stage. Look for ways to surface and celebrate unique customizations or personal artefacts by providing users with a stage to express themselves to the broader public.

---

## Sequencing

**URL Validation:** https://ui-patterns.com/patterns/Sequencing

### Problem Summary
Break down complex tasks into small and easily completed actions

### Solution
Break down complex tasks into small and easily completed actions, and set expectations as to how many steps are left before the entire sequence has been completed.

	Split up complex tasks. Lower the cognitive load needed to complete complex tasks by breaking them down into small, easily completed actions that are steps in a sequence or simply a list of items that need to be completed to advance through the system.
	Set clear objectives for subtasks. Each subtask should be specified in terms of objectives so that the whole area of interest is covered.
	Set expectations. Set expectations as to how many steps are left before the entire sequence has been completed.
	Remove what is not needed. As you break down a complex task, take note of what users need to do, what the system can do, and what information the user needs. Sequencing into multiple steps allows for conditioning the content shown depending on earlier input, potentially helping to remove steps previously deemed necessary.

### Rationale
It is easier to take action when complex activities are broken down into smaller and more manageable tasks. Our working memory has limited capacity that can temporarily hold the information needed for reasoning and the guidance of decision-making.

### Usage Examples
Break down complex tasks into small and easily completed actions, and set expectations as to how many steps are left before the entire sequence has been completed.

	Split up complex tasks. Lower the cognitive load needed to complete complex tasks by breaking them down into small, easily completed actions that are steps in a sequence or simply a list of items that need to be completed to advance through the system.
	Set clear objectives for subtasks. Each subtask should be specified in terms of objectives so that the whole area of interest is covered.
	Set expectations. Set expectations as to how many steps are left before the entire sequence has been completed.
	Remove what is not needed. As you break down a complex task, take note of what users need to do, what the system can do, and what information the user needs. Sequencing into multiple steps allows for conditioning the content shown depending on earlier input, potentially helping to remove steps previously deemed necessary.

---

## Serial Positioning Effect

**URL Validation:** https://ui-patterns.com/patterns/Serial-positioning-effect

### Problem Summary
We have a tendency to recall the first and the last items in a series best

### Solution
How do you order list items?
Present important items at the beginning and end of a list to maximize recall and the likelihood that users will remember those items when the time comes to make a decision. Initial items are remembered more efficiently than items later in a list. Items at the end of a list are recalled more easily immediately after their presentation.
Concretely, you will want to:

	Present important items at the beginning and at the end of a list to maximize recall  the probability that people will remember those items.
	If you want people to choose one item over another, present it in the end of a list if the decision is to be made immediately after its presentation. We tend to favor the last candidate presented to us.
	If the decision is to be made at a later time, present your preferred item at the beginning of the list.
	Focus on only showing information relevant to the current task in your user interface to minimize the load you put on your users cognitive capacity. Provide tools to guide your user toward their goals, helping them be more efficient and more accurate in their tasks.
	Add cues to things previously encountered in order to inititate recognition of the action and recall its meaning. Cues are most often graphical, but can also include sounds.
	Limit the amount of recall required to retain relevant information to complete a task or simply to retrieve information. Human attention is limited and we are only capable of maintaining up to around five items in our short-term memory.

### Rationale
When recalling items from a list, items at the beginning and the end are better recalled than the items in the middle.
Our ability to better recall items at the beginning of a list is called the primacy effect, whereas our ability to recall items at the end of a list is called a recency effect.

	Primacy effect: Initial items on a list are stored in long-term memory more efficiently than items later in the list. The longer the time items are presented, the stronger the primacy effect is, as people then have more time to store the initial items in long-term memory.
	Recency effect: The last few items are still in working memory and are readily available. The strength of the recency effect is unaffected by the rate of presentation, but is greatly affected by the passage of time and presentation of additional information. The recency effect further disappears when people think about other matters for thirty seconds after the last item in the list is presented.

### Usage Examples
How do you order list items?
Present important items at the beginning and end of a list to maximize recall and the likelihood that users will remember those items when the time comes to make a decision. Initial items are remembered more efficiently than items later in a list. Items at the end of a list are recalled more easily immediately after their presentation.
Concretely, you will want to:

	Present important items at the beginning and at the end of a list to maximize recall  the probability that people will remember those items.
	If you want people to choose one item over another, present it in the end of a list if the decision is to be made immediately after its presentation. We tend to favor the last candidate presented to us.
	If the decision is to be made at a later time, present your preferred item at the beginning of the list.
	Focus on only showing information relevant to the current task in your user interface to minimize the load you put on your users cognitive capacity. Provide tools to guide your user toward their goals, helping them be more efficient and more accurate in their tasks.
	Add cues to things previously encountered in order to inititate recognition of the action and recall its meaning. Cues are most often graphical, but can also include sounds.
	Limit the amount of recall required to retain relevant information to complete a task or simply to retrieve information. Human attention is limited and we are only capable of maintaining up to around five items in our short-term memory.

---

## Shopping Cart

**URL Validation:** https://ui-patterns.com/patterns/ShoppingCart

### Problem Summary
The online shopping experience needs to be realized through a real world analogy.

### Solution
A shopping cart is a collection of selected products that the user can use to manage their online shopping experience. The user can add, update and remove products from their cart. Further, the user can choose to change the quantity of each product in the shopping cart. A subtotal cost is displayed for each of the items in the cart plus shipping charges, VAT, etc. At any time, the user can choose to continue shopping or proceed to checkout – meaning to paying and ordering what is in the shopping cart.
Whenever a product is presented, a complimenting “add to cart” button should be visible , this lets the user add the respective product to the product cart. The contents of the cart can viewed at any time, in detail by clicking on a “show cart” link.
When the user chooses to checkout, he is presented with a final list of items on the order, as well as payment options (credit card, wire transfer or cash on delivery).

### Rationale
The shopping cart is a well known metaphor for shopping online. The metaphor provides the user with the idea, that putting items in the shopping cart does not necessarily mean that he or she is buying those items, as they can be removed before checking out of the store. The shopping cart pattern allows the user to collect a number of items first in order to pay for them all at a later time. The checkout metaphor goes well with the shopping cart as it resembles the process at a real super market.

### Usage Examples
A shopping cart is a collection of selected products that the user can use to manage their online shopping experience. The user can add, update and remove products from their cart. Further, the user can choose to change the quantity of each product in the shopping cart. A subtotal cost is displayed for each of the items in the cart plus shipping charges, VAT, etc. At any time, the user can choose to continue shopping or proceed to checkout – meaning to paying and ordering what is in the shopping cart.
Whenever a product is presented, a complimenting “add to cart” button should be visible , this lets the user add the respective product to the product cart. The contents of the cart can viewed at any time, in detail by clicking on a “show cart” link.
When the user chooses to checkout, he is presented with a final list of items on the order, as well as payment options (credit card, wire transfer or cash on delivery).

---

## Shortcut Dropdown

**URL Validation:** https://ui-patterns.com/patterns/ShortcutDropdown

### Problem Summary
The user needs to access a specific section or functionality of a website in a quick way regardless of hierarchy.

### Solution
Add a combobox (a select box in HTML to list a number of fixed locations (URLS) on one or more pages. When the form is submitted, the user is redirected to the chosen page.
	An alternate version is to redirect to the chosen page as soon as the user selects an item from the combobox and not when he submits the form.

### Rationale
The often hierarchical structure of a website can at times impede the path to specific functionality of a website. By adding a shortcut to the most frequently used functionality, the path can be shortened: the number of clicks can be lessened and the confusion decreased.

### Usage Examples
Add a combobox (a select box in HTML to list a number of fixed locations (URLS) on one or more pages. When the form is submitted, the user is redirected to the chosen page.
	An alternate version is to redirect to the chosen page as soon as the user selects an item from the combobox and not when he submits the form.

---

## Simulation

**URL Validation:** https://ui-patterns.com/patterns/Simulation

### Problem Summary
Give people first-hand insight into how inputs affect an output

### Solution
Simulate cause-and-effect. Clearly and quickly show cause-and-effect relationships to allow users to explore and experiment without being overly instructional.
	Simulate an environment. Create situations that reward and motivate people for a specific behavior as you allow users to rehearse and practice a target behavior in a safe setting. Simulating an environment can help you facilitate role-playing, adopting another persons perspective, and control exposure to new or frightening situations.
	Simulate context. Make the impact on normal life clear by creating a simulation of a context. Although it might be costly and complicated, simulating the context itself will make the persuasion less dependent on imagination or disbelief and individual implications clearer.

### Rationale
Simulation enables users to observe the link between cause and effect in real time. The rules used to simulate outcomes are based on assumptions and as such have persuasive power. Simulation can serve as a great learning tool, as it enables users to try out behavior they wouldnt dare in the real world.

### Usage Examples
Simulate cause-and-effect. Clearly and quickly show cause-and-effect relationships to allow users to explore and experiment without being overly instructional.
	Simulate an environment. Create situations that reward and motivate people for a specific behavior as you allow users to rehearse and practice a target behavior in a safe setting. Simulating an environment can help you facilitate role-playing, adopting another persons perspective, and control exposure to new or frightening situations.
	Simulate context. Make the impact on normal life clear by creating a simulation of a context. Although it might be costly and complicated, simulating the context itself will make the persuasion less dependent on imagination or disbelief and individual implications clearer.

---

## Slideshow

**URL Validation:** https://ui-patterns.com/patterns/Slideshow

### Problem Summary
A collection of media needs to be displayed in a presentation as a sequence of still images.

### Solution
A slideshow shows several stories with images, one at a time. After a specific time interval one story is replaced by another  often with an animated transition.
Transitions
Transitions between images are most often a sliding effect although a simple fade is also a popular choice. The most important design choice when it comes to transitions is to make it seem natural. Animations should never be used for showing off; only to support the usability and understandability of UI.
Numbers, bullets, or thumbnails
Use numbers, bullets, squares, or thumbnails to represent all the images in the slideshow. These provide a visual mechanism for navigation and serve as indicators for slides seen and slides still remaining to be seen. Numbers, bullets, and thumbnails help set expectations of what is to come.
Use numbers if its important to let the user now exactly how many stories a slideshow has. Use bullets if it doesnt matter, and thumbnails if you want to inspire the user to jump past the sequential order of stories that youve chosen beforehand.
Focus attention
Slideshows steal attention! Especially if they are combined with animated transitions. Put slideshows together with blinking advertisement and other bright, animated or otherwise attention-stealing elements on the page and you have mayhem. If more than one element screams for attention, the user will get lost. If you have multiple elements that scream for attention other than the slideshow, the slideshow will only help diffuse users attention instead of focusing it.
Consider whether your slideshow is going to represent the main and most important stories of your site  if it doesnt, then leave out the slideshow. A slideshow directs attention towards itself. Dont overdo it.
Buttons and good callout texts
Increase the effectiveness of your slideshow by adding buttons for each story that calls out for attention. Buttons help users know what to click. However, be careful not to fall in the common trap of just labelling your button with Read more, unless that is really the only action the user can do by clicking on that button. Texts like Support, Donate, Buy, and Watch video are much more effective in getting users to click and set expectations of what they will get.
Navigation
Common navigation elements include:

	Previous and next buttons
	Bullets, numbers, or thumbnails
	Callout buttons

In order not to present the user with too many options at first, consider hiding navigational elements (such as previous and next buttons) until users hover the slideshow image. Too many options at first can confuse users and make them go away before they even got started. Reveal their options as their interest is sparked.
Full image or tabs with title
Slideshows usually fall into one of the following categories:

	Either the image of the story fills the entire slideshow. The current story is represented by a big image that acts as a background with text on top. This version provide the biggest sensory experience as it focuses on as large images as possible.
	Or the stories in the slideshow is listed either horizontally or vertically on the side or below or on top of the image. This version focus on conveying titles and text more than a visual sensory experience. Use this type if the title of a story is so important that the user cant wait till that one story is up.

### Rationale
Slideshows highlight several different stories on the same screen real estate. They allow users to quickly skim through stories. Slideshows capture the user’s attention and retain attention with simple navigation, captivating content and calls to action. They focus users attention sharply on the content instead of interacting with the browser.

### Usage Examples
A slideshow shows several stories with images, one at a time. After a specific time interval one story is replaced by another  often with an animated transition.
Transitions
Transitions between images are most often a sliding effect although a simple fade is also a popular choice. The most important design choice when it comes to transitions is to make it seem natural. Animations should never be used for showing off; only to support the usability and understandability of UI.
Numbers, bullets, or thumbnails
Use numbers, bullets, squares, or thumbnails to represent all the images in the slideshow. These provide a visual mechanism for navigation and serve as indicators for slides seen and slides still remaining to be seen. Numbers, bullets, and thumbnails help set expectations of what is to come.
Use numbers if its important to let the user now exactly how many stories a slideshow has. Use bullets if it doesnt matter, and thumbnails if you want to inspire the user to jump past the sequential order of stories that youve chosen beforehand.
Focus attention
Slideshows steal attention! Especially if they are combined with animated transitions. Put slideshows together with blinking advertisement and other bright, animated or otherwise attention-stealing elements on the page and you have mayhem. If more than one element screams for attention, the user will get lost. If you have multiple elements that scream for attention other than the slideshow, the slideshow will only help diffuse users attention instead of focusing it.
Consider whether your slideshow is going to represent the main and most important stories of your site  if it doesnt, then leave out the slideshow. A slideshow directs attention towards itself. Dont overdo it.
Buttons and good callout texts
Increase the effectiveness of your slideshow by adding buttons for each story that calls out for attention. Buttons help users know what to click. However, be careful not to fall in the common trap of just labelling your button with Read more, unless that is really the only action the user can do by clicking on that button. Texts like Support, Donate, Buy, and Watch video are much more effective in getting users to click and set expectations of what they will get.
Navigation
Common navigation elements include:

	Previous and next buttons
	Bullets, numbers, or thumbnails
	Callout buttons

In order not to present the user with too many options at first, consider hiding navigational elements (such as previous and next buttons) until users hover the slideshow image. Too many options at first can confuse users and make them go away before they even got started. Reveal their options as their interest is sparked.
Full image or tabs with title
Slideshows usually fall into one of the following categories:

	Either the image of the story fills the entire slideshow. The current story is represented by a big image that acts as a background with text on top. This version provide the biggest sensory experience as it focuses on as large images as possible.
	Or the stories in the slideshow is listed either horizontally or vertically on the side or below or on top of the image. This version focus on conveying titles and text more than a visual sensory experience. Use this type if the title of a story is so important that the user cant wait till that one story is up.

---

## Social Proof

**URL Validation:** https://ui-patterns.com/patterns/Social-proof

### Problem Summary
We assume the actions of others in new or unfamiliar situations

### Solution
Highlight the same social activity on your website that you want your users to conduct. Consider what kind of your behavior you want users to perform and find ways to show social proof of that exact behavior.
There are several ways to highlight what is the more correct behavior. Let us look at how we can appeal to users logic, emotions, and belief in your credibility.
6 ways to use Social Proof
You can play on social proof in a large variety of ways. Here’s just a few for inspiration.

	Expert social proof. Approval from a credible expert, like a magazine or blogger, can have incredible digital influence.


	Celebrity social proof. A strong identification with celebrities effectively drives decisions.


	Customer social proof. Simply displaying the logos of your most prominent and recognisable customers will let potential customers know that they are in good company.


	User social proof. Testimonials and proof of user action help guide users into making a decision.


	Wisdom of crowds. Highlighting popularity or large numbers of users implies “they can’t all be wrong.”


	Wisdom of friends. We prefer to say yes to the requests of someone we know and like.

Appeal to logic, emotions, and to ethical character
Appealing to facts and logic
Communicate social proof through facts, statistics, and logic. Common examples on community sites are 8 people liked this, 434 viewed this image, or this blog post has 12 comments. Subjectivity can also be communicated quantitatively: 4 out of 5 stars or 92% liked this.
Social proof helps us determine what is good behavior on a given website and is thus crucial for getting first-time users started. Last.fm uses leaderboards of their most played music by genre to guide visitors and getting them started with listening to great music.
Web applications often have pricing plans highlighting the companys most wanted subscription plan with a most popular plan tag line in the hopes having users in doubt of which plan to choose select just that plan.
Appealing to emotions
Emotions have the power to modify our judgments, why appealing to emotions can help burst positive arguments or dampen negative arguments.
Cater to peoples emotions by listing testimonials of people who like your product. If you want to assure potential customers that your product is worth its price, then list testimonials from satisfied paying customers.
Appealing to ethics, moral, and character
Your audience will judge your propositions as being more true and acceptable if you succeed to establish your credibility.

	Use role models. Learn who your audience looks up to and compares itself to and seek out positive role models to guide their behavior. The authority of experts or influential people similarity of friends and audience can drive behavior. Testimonials, expert quotations, and statistics are efficient ways to communicate.


	Present social evidence next to Call to Actions. Provide mental shortcuts for users to decide through social evidence of the previous decisions of others. Use testimonials, expert quotations, and statistics to encourage desired behaviors.


	Similarities between group and self. People are more likely to conform to a group’s behavior if they perceive themselves belonging to the same or similar group. Communicate characteristics relevant to the users segment or context, such as related behavior, proximity, gender or age, interests, or profession to influence behavior.

### Rationale
We have a common tendency to adopt the opinions and follow the behaviors of the majority to feel safer and to avoid conflict.
Social Proof establishes the norm others follow through experts, celebrities, the crowd, friends, or similar users. Communicate Social Proof testimonials, expert quotations, related actions by friends, or statistics like number of views, followers, or comments to encourage desired behaviors.
The actions of those around us are important when we decide what constitutes correct behavior. Whether it is to choose between two restaurants, to litter on the street, how fast to drive in a certain stretch on the highway, or which youtube video to watch first, we look to those around us to determine the correct answer.
Assuming that those around us are behaving normally, we will make fewer mistakes by acting in accord with social evidence than contrary to it. Acting in accord with social evidence is a shortcut to correct behavior and an often good decision.
Social proof is so effective as most of us would rather imitate that initiate. Independent thought requires expensive brain energy, why we often resort to short-cutting our thought processes where we can.
Your audience will judge your propositions as being more true and acceptable if you succeed to establish your credibility. Especially if your product is new, it’s critical to establish credibility with potential customers
Related studies
In 1951, Salomon Asch5 set up an experiment to prove social proof.
The setup: Entering a room together with a conferederate assumed to be other participants, 50 young adults were shown a depecting a target line next to three lines A, B, C and asked which was most similar in length to the target line. Although the answer was always obvious, the confederaates purposefully gave the wrong answer before the participant.
The result: Over 12 trials, participants conformed at least once 75% of the time.

### Usage Examples
Highlight the same social activity on your website that you want your users to conduct. Consider what kind of your behavior you want users to perform and find ways to show social proof of that exact behavior.
There are several ways to highlight what is the more correct behavior. Let us look at how we can appeal to users logic, emotions, and belief in your credibility.
6 ways to use Social Proof
You can play on social proof in a large variety of ways. Here’s just a few for inspiration.

	Expert social proof. Approval from a credible expert, like a magazine or blogger, can have incredible digital influence.


	Celebrity social proof. A strong identification with celebrities effectively drives decisions.


	Customer social proof. Simply displaying the logos of your most prominent and recognisable customers will let potential customers know that they are in good company.


	User social proof. Testimonials and proof of user action help guide users into making a decision.


	Wisdom of crowds. Highlighting popularity or large numbers of users implies “they can’t all be wrong.”


	Wisdom of friends. We prefer to say yes to the requests of someone we know and like.

Appeal to logic, emotions, and to ethical character
Appealing to facts and logic
Communicate social proof through facts, statistics, and logic. Common examples on community sites are 8 people liked this, 434 viewed this image, or this blog post has 12 comments. Subjectivity can also be communicated quantitatively: 4 out of 5 stars or 92% liked this.
Social proof helps us determine what is good behavior on a given website and is thus crucial for getting first-time users started. Last.fm uses leaderboards of their most played music by genre to guide visitors and getting them started with listening to great music.
Web applications often have pricing plans highlighting the companys most wanted subscription plan with a most popular plan tag line in the hopes having users in doubt of which plan to choose select just that plan.
Appealing to emotions
Emotions have the power to modify our judgments, why appealing to emotions can help burst positive arguments or dampen negative arguments.
Cater to peoples emotions by listing testimonials of people who like your product. If you want to assure potential customers that your product is worth its price, then list testimonials from satisfied paying customers.
Appealing to ethics, moral, and character
Your audience will judge your propositions as being more true and acceptable if you succeed to establish your credibility.

	Use role models. Learn who your audience looks up to and compares itself to and seek out positive role models to guide their behavior. The authority of experts or influential people similarity of friends and audience can drive behavior. Testimonials, expert quotations, and statistics are efficient ways to communicate.


	Present social evidence next to Call to Actions. Provide mental shortcuts for users to decide through social evidence of the previous decisions of others. Use testimonials, expert quotations, and statistics to encourage desired behaviors.


	Similarities between group and self. People are more likely to conform to a group’s behavior if they perceive themselves belonging to the same or similar group. Communicate characteristics relevant to the users segment or context, such as related behavior, proximity, gender or age, interests, or profession to influence behavior.

---

## Sort By Column

**URL Validation:** https://ui-patterns.com/patterns/SortByColumn

### Problem Summary
The user needs to be able to sort the data in a table according to the values of a column.

### Solution
Extend the table functionality so that each column table heading is a link. When the heading is clicked, the rows in the table are ordered ascending by the specific columns values. If the same label heading is clicked again, the order is reversed: the rows in the table are ordered descending by the specific columns values.
When the rows of a table have been sorted by a specific column, an arrow is often displayed beside the columns heading indicating the direction the rows have been sorted in. The columns heading is often presented in another font color or font weight (bold / regular) to indicate ordering has been performed.

### Rationale
The pattern provides an easy way to organize and compare data in a table. Furthermore, the pattern is also well known from desktop applications dealing with rows of data.

### Usage Examples
Extend the table functionality so that each column table heading is a link. When the heading is clicked, the rows in the table are ordered ascending by the specific columns values. If the same label heading is clicked again, the order is reversed: the rows in the table are ordered descending by the specific columns values.
When the rows of a table have been sorted by a specific column, an arrow is often displayed beside the columns heading indicating the direction the rows have been sorted in. The columns heading is often presented in another font color or font weight (bold / regular) to indicate ordering has been performed.

---

## Status

**URL Validation:** https://ui-patterns.com/patterns/Status

### Problem Summary
We constantly look to how our actions improve or impair how others see us

### Solution
Regardless of our income or social standing, we look for ways to improve and retain our status. We crave belonging and gathering status labels reinforces this. Acknowledging a persons position in a group can inject confidence in the individual and act as a behavioral reference point for others.

	Let users gauge and express their standing. Provide feedback loops and measures to let people know how they are doing and consider how you can give users a chance to express it. Highlight successful acts that others should follow and provide positive feedback when others follow suit.
	Let users protect their status. We act when our status seems in jeopardy, so be careful not to present status linked to undesired behavior.
	Show relative status. The status level of a user only has meaning if it is relative to status levels of other users on the platform. Status can work in levels, although it does not have to be hierarchical. Consider branching out status to let users take on various roles.

Status relates to our standing relative to others or our personal best and can be both personal (income, performance, etc.) and public (scoring, recognition, etc.).

### Rationale
We constantly assess our social or professional standing relative to others, seeing how interactions either enhance or diminish it

### Usage Examples
Regardless of our income or social standing, we look for ways to improve and retain our status. We crave belonging and gathering status labels reinforces this. Acknowledging a persons position in a group can inject confidence in the individual and act as a behavioral reference point for others.

	Let users gauge and express their standing. Provide feedback loops and measures to let people know how they are doing and consider how you can give users a chance to express it. Highlight successful acts that others should follow and provide positive feedback when others follow suit.
	Let users protect their status. We act when our status seems in jeopardy, so be careful not to present status linked to undesired behavior.
	Show relative status. The status level of a user only has meaning if it is relative to status levels of other users on the platform. Status can work in levels, although it does not have to be hierarchical. Consider branching out status to let users take on various roles.

Status relates to our standing relative to others or our personal best and can be both personal (income, performance, etc.) and public (scoring, recognition, etc.).

---

## Status-Quo Bias

**URL Validation:** https://ui-patterns.com/patterns/Statusquo-bias

### Problem Summary
We tend to accept the default option instead of comparing the actual benefit to the actual cost

### Solution
Frame the option you would like your user to choose as the default option and make the cognitive load to understand alternative options too big to comprehend at a glance.
When the user has a number of options to choose from, you can help him or her on the way by framing one of the options as the default option.
When the user has a number of options to choose from, you can help him or her on the way by framing one of the options as the default option. Lets say you run a subscription based web application with several plans, each with its own price and list of benefits. A popular plan is going to be dropped in favor of one with a higher price and better list of benefits, which leaves the users to either downgrade or upgrade; loosing old features or gaining new. Moving everybody to the new plan and framing it as being the same with new features positions the status quo reference point to the bigger plan, with the result that most people will stay.
Facebook utilized the status-quo bias in December 2009, when they changed their user privacy policy. They changed a users privacy settings into having a default setting which the user had to opt-out from. The complicated and non-transparent nature of the new policy kept users from changing them.
Apply the status-quo bias

	Limit choice. More choice is not always better. Having many choices might grab our attention, but too many can overwhelm us to the point where we are likely to not choose (or buy) at all. Complexity delays choice, further increasing the fraction of consumers, who will adopt the default options.
	Pre-select your wanted response. When the user has a number of options to choose from, you can help him or her on the way by framing one of the options as the default option. Understanding and compariing multiple options takes its toll on our cognitive load.
	Beat the bias. If you want people to change, show them the cost of staying the same, as well as potential gains. Paint a clear and visual contrast between their current state and desired future state. Consider telling a before-and-after hero story to identify with highlighting challenges relevant to the audience.

### Rationale
When we are uncertain of what to do or feel overwhelmed by the number of options to choose from, we tend to stick with our previous choices or choices that has been made for us – even if the alternatives might be better. As making decisions grows increasingly more complex, the harder it becomes to use our emotional heuristics to shortcut decision making to approximate rational thinking.
Simply stating what options are more popular is often enough to influence a decision that sticks. Simply pre-filling a form with default options is often enough to make people choose them. Alternative options that seem too cumbersome to comprehend will make people stick with the status quo.
As making decisions grows increasingly more complex, we have a harder time using our emotional heuristics to shortcut decision making to approximate rational thinking. Instead we tend to accept the default option instead of comparing the actual benefit [gain] to the actual cost [loss]1.

### Usage Examples
Frame the option you would like your user to choose as the default option and make the cognitive load to understand alternative options too big to comprehend at a glance.
When the user has a number of options to choose from, you can help him or her on the way by framing one of the options as the default option.
When the user has a number of options to choose from, you can help him or her on the way by framing one of the options as the default option. Lets say you run a subscription based web application with several plans, each with its own price and list of benefits. A popular plan is going to be dropped in favor of one with a higher price and better list of benefits, which leaves the users to either downgrade or upgrade; loosing old features or gaining new. Moving everybody to the new plan and framing it as being the same with new features positions the status quo reference point to the bigger plan, with the result that most people will stay.
Facebook utilized the status-quo bias in December 2009, when they changed their user privacy policy. They changed a users privacy settings into having a default setting which the user had to opt-out from. The complicated and non-transparent nature of the new policy kept users from changing them.
Apply the status-quo bias

	Limit choice. More choice is not always better. Having many choices might grab our attention, but too many can overwhelm us to the point where we are likely to not choose (or buy) at all. Complexity delays choice, further increasing the fraction of consumers, who will adopt the default options.
	Pre-select your wanted response. When the user has a number of options to choose from, you can help him or her on the way by framing one of the options as the default option. Understanding and compariing multiple options takes its toll on our cognitive load.
	Beat the bias. If you want people to change, show them the cost of staying the same, as well as potential gains. Paint a clear and visual contrast between their current state and desired future state. Consider telling a before-and-after hero story to identify with highlighting challenges relevant to the audience.

---

## Steps Left

**URL Validation:** https://ui-patterns.com/patterns/StepsLeft

### Problem Summary
The user is about to go through the process of filling in data over several steps and is in need of guidance.

### Solution
Add a navigation block describing the steps involved in submitting data to the system. The block should always appear on the page. As the user progresses through the process, the navigation block is updated accordingly. The current step is highlighted, giving a clear indication to the user how far they have come and how much further there is to go.
Remove unnecessary distractions like extra navigation, advertisements, and the likes.

### Rationale
The Steps Left pattern is used when it is critical to maintain the users focus throughout the process of filling in data to the system. This is for instance critical in e-commerce websites, where the checkout process is often guided by this pattern. In e-commerce websites, the checkout process is the most critical part of the site, as this is the part that captures the customers money. The Steps Left pattern provide the user with a great overview of how far in the process the user has gone: it provides a visible end to the process, which the user can aim for.
This pattern is similar to the Wizard pattern most commonly found in desktop applications, which guide the user step by step.

### Usage Examples
Add a navigation block describing the steps involved in submitting data to the system. The block should always appear on the page. As the user progresses through the process, the navigation block is updated accordingly. The current step is highlighted, giving a clear indication to the user how far they have come and how much further there is to go.
Remove unnecessary distractions like extra navigation, advertisements, and the likes.

---

## Storytelling

**URL Validation:** https://ui-patterns.com/patterns/Storytelling

### Problem Summary
Use the narrative qualities of storytelling to let the user engage in a perspective

### Solution
Stories can be explicit and simple narratives or implied in the words you use.
For effective use of storytelling in design, consider to:

	Create a plot, with conflict. Transform your users into heroes and obstacles into villains as you frame how they can overcome specific problems using your design.
	Make your users part of the story. Transfer the emotional power of the narrative to your users by letting them be actors in your story.
	Make your story episodic. Part the storyline, evolution of the user, or learning journey into episodic parts to continuously reward users with chapter endings, keep users in a state of craving more, and adjust for the users rising skill level as episodes or levels get harder.

It is easier for you to work on your product becoming part of an existing narrative and making sure it plays a positive role  than than trying to create a new narrative itself from ground up.

### Rationale
Our understanding of the world is shaped by the stories were told. Consequently, we filter our decisions through stories, whether they are real or imagined.
Stories can be explicit and simple narratives or implied in the words you use. The most powerful stories are well-crafted visions that give significance to mundane tasks.
Stories excite. The most powerful stories are well-crafted visions that give significance to mundane tasks.

### Usage Examples
Stories can be explicit and simple narratives or implied in the words you use.
For effective use of storytelling in design, consider to:

	Create a plot, with conflict. Transform your users into heroes and obstacles into villains as you frame how they can overcome specific problems using your design.
	Make your users part of the story. Transfer the emotional power of the narrative to your users by letting them be actors in your story.
	Make your story episodic. Part the storyline, evolution of the user, or learning journey into episodic parts to continuously reward users with chapter endings, keep users in a state of craving more, and adjust for the users rising skill level as episodes or levels get harder.

It is easier for you to work on your product becoming part of an existing narrative and making sure it plays a positive role  than than trying to create a new narrative itself from ground up.

---

## Structured Format

**URL Validation:** https://ui-patterns.com/patterns/StructuredFormat

### Problem Summary
The user needs to quickly enter data into the system but the format of the data must adhere to a predefined structure.

### Solution
Represent input fields in a way that clearly guides or limits the user as to what input format to use.
An input field is presented with an accompanying label describing the input that is expected in the field. The label describes a specific structure the user must follow to input a valid value.
In some cases the user is presented with the possibility to use helping mechanisms such as a date selection calendar to fill out the input box in the correct way. When the user has done this multiple times, they slowly learn how the input is formatted, so that they can copy the same format on their own.

### Rationale
Set clear expectations by ordering input fields in a Structured Format: clue users as to what kind of input is being requested. By chunking large input fields into smaller bits, data entry errors can be decreased dramatically. It is easier to transcribe or memorize a long number when it is broken up into chunks. Where the Structured Format is well suited for predictable input, the Forgiving Format is well suited for open-ended input.
Using a structured format in an input field saves time for the user, when they are required to fill out the same input field repeatedly as a part of a frequent task. The structured data pattern aids the user through streamlined and controlled inputs, which in turn speeds up data capturing tasks and reduces the garbage in, garbage out problem.

### Usage Examples
Represent input fields in a way that clearly guides or limits the user as to what input format to use.
An input field is presented with an accompanying label describing the input that is expected in the field. The label describes a specific structure the user must follow to input a valid value.
In some cases the user is presented with the possibility to use helping mechanisms such as a date selection calendar to fill out the input box in the correct way. When the user has done this multiple times, they slowly learn how the input is formatted, so that they can copy the same format on their own.

---

## Table Filter

**URL Validation:** https://ui-patterns.com/patterns/TableFilter

### Problem Summary
The user needs to categorical filter the data displayed in tables by the columns.

### Solution
Provide dropdown inputs that present the categories by which the user can filter the data set by. Once the user selects a category and clicks Filter or something similar (when the user submits the form), only the row that belong to the selected category are displayed.
Optionally, multiple filters can be added. If this solution is chosen, you must be aware to update the categories of each dropdown box accordingly when one category is selected  as the selecting values in one category might reduce the options left in another.

### Rationale
Adding filters to your tables lets the user reduce the amount of items shown. Filters help narrow down search results, letting the user find more accurate results.

### Usage Examples
Provide dropdown inputs that present the categories by which the user can filter the data set by. Once the user selects a category and clicks Filter or something similar (when the user submits the form), only the row that belong to the selected category are displayed.
Optionally, multiple filters can be added. If this solution is chosen, you must be aware to update the categories of each dropdown box accordingly when one category is selected  as the selecting values in one category might reduce the options left in another.

---

## Tagging

**URL Validation:** https://ui-patterns.com/patterns/Tag

### Problem Summary
Items need to be labelled, categorized, and organized using keywords that describe them.

### Solution
Let users associate multiple topics with a piece of content. Allow users to add appropriate keywords to categorize their own content in a non-hierarchical way. Let users use hashtags to integrate tagging into the content itself.
Allow keywords to be associated with items on a website/application such as blog articles, ecommerce products and media. Use terms that categorically describe these items. Permit these items to be found in a search using these keywords. Let contributors of information add keywords to the content they submit. Keywords can be displayed as links that aid in finding items with matching keywords.

### Rationale
Tagging helps make it easier for users to find their own content and for their peers to discover content related to their interests.
Tags are relevant keywords associated with or assigned to a piece of information. Tags are often used on social websites, where users can upload their own content. Here, tags are used to let users organize and categorize their own data in the public sphere. In this way, tags can be seen as a bottom-up categorization of data rather than a top-down categorization of data, where the creators of the site define the hierarchy data is submitted to.

### Usage Examples
Let users associate multiple topics with a piece of content. Allow users to add appropriate keywords to categorize their own content in a non-hierarchical way. Let users use hashtags to integrate tagging into the content itself.
Allow keywords to be associated with items on a website/application such as blog articles, ecommerce products and media. Use terms that categorically describe these items. Permit these items to be found in a search using these keywords. Let contributors of information add keywords to the content they submit. Keywords can be displayed as links that aid in finding items with matching keywords.

---

## Tag Cloud

**URL Validation:** https://ui-patterns.com/patterns/TagCloud

### Problem Summary
The user wants to browse content by popularity in a visually appealing way.

### Solution
A tag cloud is a list of tags, where the font size of each tag is larger or bigger depending on its weight. Weight in tag clouds can be represented in three different ways:

	Size represents the number of times that a tag has been applied to a single item.
This kind of tag cloud can help define the distribution of how the item is categorized.
	Size represents the number of items to which a tag has been applied
As a presentation of each tags popularity.
	Size represents the quantity of content items in that category
Tags are used as a categorization method for content items1

There are several opinions on how tags should be ordered. Examples of ways to order tags are:

	Alphabetically
	Randomly
	By weight
	In clusters of semantically similar tags (similar tags appear next to eachother)

### Rationale
Tag clouds helps visualize semantic fields; how some categories have greater importance than others.
It can also help give an impression of what content is to be found on a site and which categories of content the site is focused on.

### Usage Examples
A tag cloud is a list of tags, where the font size of each tag is larger or bigger depending on its weight. Weight in tag clouds can be represented in three different ways:

	Size represents the number of times that a tag has been applied to a single item.
This kind of tag cloud can help define the distribution of how the item is categorized.
	Size represents the number of items to which a tag has been applied
As a presentation of each tags popularity.
	Size represents the quantity of content items in that category
Tags are used as a categorization method for content items1

There are several opinions on how tags should be ordered. Examples of ways to order tags are:

	Alphabetically
	Randomly
	By weight
	In clusters of semantically similar tags (similar tags appear next to eachother)

---

## Tailoring

**URL Validation:** https://ui-patterns.com/patterns/Tailoring

### Problem Summary
Adapt the offerings of a system to match individual users’ needs and abilities

### Solution
Tailor information to users individually. Content will be more persuasive if it is tailored to the individual needs, interests, personality, or usage context.

	Boost credibility. Tailoring the user experience has been proven to lead to increased perception of credibility. A website is seen as more credible when it acknowledges that an individual has visited before.
	Personally tailor information in real time. Provide information that matches the personal needs, interests, personality, or goals of the user. The more relevant the message is to the individual the higher persuasive power it will have.
	Tailor for the context. The more you can utilize the context and intention of the individual, the more relevant your message can be to not only the person, but also the context.

### Rationale
Tailored information is more effective in changing attitudes and beliefs than generic information. Make life simpler for users by showing only what is relevant to them. Tailor to individual needs, interests, personality, usage context, or other factors relevant to the individual.
Users are persuaded either through a central route, with full cognitive attention, or through a peripheral route, relying on heuristics

### Usage Examples
Tailor information to users individually. Content will be more persuasive if it is tailored to the individual needs, interests, personality, or usage context.

	Boost credibility. Tailoring the user experience has been proven to lead to increased perception of credibility. A website is seen as more credible when it acknowledges that an individual has visited before.
	Personally tailor information in real time. Provide information that matches the personal needs, interests, personality, or goals of the user. The more relevant the message is to the individual the higher persuasive power it will have.
	Tailor for the context. The more you can utilize the context and intention of the individual, the more relevant your message can be to not only the person, but also the context.

---

## Thumbnail

**URL Validation:** https://ui-patterns.com/patterns/Thumbnail

### Problem Summary
The user needs to get an overview of multiple pictures without having to download each of the full size images.

### Solution
A thumbnail is a miniature version of a larger picture. The thumbnail can illustrate anything graphical: a picture, movie or even a screenshot of a webpage.The dimensions (width and height) of multiple thumbnails appearing next to each other are the exact same. In order to preserve the same proportions in the thumbnail image as were found in the original image, both resizing and cropping is part of the image manipulation process.
Common thumbnail sizes are:

	
		Dimension (width X height) 
		Description 
	
	
		 4848 
		 Very small 
	
	
		 6464 
		 Small 
	
	
		 8080 
		 Medium 
	
	
		 9696 
		 Medium 
	
	
		 128128 
		 Large 
	
	
		 144144 
		 Extra large 
	
	
		 160160 
		 Super Large

### Rationale
Using thumbnails provides the user with an overview of several images or movies in the space of one web page. Furthermore, thumbnails save bandwidth as the user does not have to click through all images to find the one he or she is looking for, but can be guided by the previews provided by the thumbnails.

### Usage Examples
A thumbnail is a miniature version of a larger picture. The thumbnail can illustrate anything graphical: a picture, movie or even a screenshot of a webpage.The dimensions (width and height) of multiple thumbnails appearing next to each other are the exact same. In order to preserve the same proportions in the thumbnail image as were found in the original image, both resizing and cropping is part of the image manipulation process.
Common thumbnail sizes are:

	
		Dimension (width X height) 
		Description 
	
	
		 4848 
		 Very small 
	
	
		 6464 
		 Small 
	
	
		 8080 
		 Medium 
	
	
		 9696 
		 Medium 
	
	
		 128128 
		 Large 
	
	
		 144144 
		 Extra large 
	
	
		 160160 
		 Super Large

---

## Tip A Friend

**URL Validation:** https://ui-patterns.com/patterns/TipAFriend

### Problem Summary
The user wants to share something of interest with a peer.

### Solution
Add a link with a similar text to “Tip a friend”, “Send this to a friend”, “Share this with a friend”, that leads to a form to be filled out with the user’s data as well as a private message. The result of the form could be a mail sent out to the user’s friend with a condensed formed version of the content or simply a link to the original content.

### Rationale
The Tip A Friend pattern is a function that facilitates the user’s need to easily spread the word about content. It can be useful if the information of interest is formatted in a way, that makes it hard to copy-paste into an understandable mail. The website can then help format the mail by setting up the info in a nice and readable format.
The usefulness of this pattern when just letting the user send a blank mail with a link to the content in question, can be debated. The users need for this kind of functionality is often not justified.

### Usage Examples
Add a link with a similar text to “Tip a friend”, “Send this to a friend”, “Share this with a friend”, that leads to a form to be filled out with the user’s data as well as a private message. The result of the form could be a mail sent out to the user’s friend with a condensed formed version of the content or simply a link to the original content.

---

## Walkthrough

**URL Validation:** https://ui-patterns.com/patterns/Tour

### Problem Summary
The user wants to learn the products and services you offer in order to make a decision to join a service or buy a product.

### Solution
Present the main features of your product before the user starts using it. Present your product and/or value proposition before the real user experience begins. Walkthroughs are often presented as either a static or animated slideshow or with video. Keep it short and to the point as users often skip or breeze through in order to get started.
A Walkthrough explains a product or service in terms of features, benefits, and in general what the product or service allows you to do. It is most often split into more than one section, which is sometimes put on separate pages.
With this in mind, here are a few principles to keep in mind when developing a Walkthrough.
Focus on users tasks
Whether the Walkthrough is strictly a marketing tool or a tool to teach, a focus on the users tasks is important. How can you help them? Aim for a good balance between only describing essentials and explaining everything. Only describing essentials might not give users an elaborate enough view of your product to aid their decision to engage with your product. If you are too elaborate you might on the other hand scare then away.
Resist the urge to show off the latest and greatest features  the most important thing is to convince your users that your product will help them with their fundamental problems. New users arent interested in your bells and whistles; they just want to accomplish their goals1.
Provide visual references
Dont just write about your product and its features. Show it! Include screenshots, illustrations, and even video clips of how to use your product.
This will allow your users to get a better feeling of where exactly to click  but also how easy your product actually is  how it was meant to work and be used.
Include direct links
As users use Walkthroughs to learn about your product or service, they will go back and forth between the Walkthrough and the product. It is their reference point, so make it easy for them to go back and forth between the two. Provide direct links, if possible, to the sections you explain.
Address issues or concerns up front
Address the top concerns your users might have when they are trying to decide whether or not to use your product or not. Is it safe, Can I import my data easily?, Can I export my data if I decide to move?. Put any concerns to rest so that your users can start using your product or service with confidence.

### Rationale
A Walkthrough of your product or service helps inform users about:

	What your product can do
	If your product is what theyve been looking for
	If your product will help users accomplish their tasks
	Whether or not they should join your service or pay for your product

Purchasing a product or service can be costly and users will need a significant amount of persuasion and encouragement before buying in. A Walkthrough allows users to get a glimpse of your product without having to sign up.

### Usage Examples
Present the main features of your product before the user starts using it. Present your product and/or value proposition before the real user experience begins. Walkthroughs are often presented as either a static or animated slideshow or with video. Keep it short and to the point as users often skip or breeze through in order to get started.
A Walkthrough explains a product or service in terms of features, benefits, and in general what the product or service allows you to do. It is most often split into more than one section, which is sometimes put on separate pages.
With this in mind, here are a few principles to keep in mind when developing a Walkthrough.
Focus on users tasks
Whether the Walkthrough is strictly a marketing tool or a tool to teach, a focus on the users tasks is important. How can you help them? Aim for a good balance between only describing essentials and explaining everything. Only describing essentials might not give users an elaborate enough view of your product to aid their decision to engage with your product. If you are too elaborate you might on the other hand scare then away.
Resist the urge to show off the latest and greatest features  the most important thing is to convince your users that your product will help them with their fundamental problems. New users arent interested in your bells and whistles; they just want to accomplish their goals1.
Provide visual references
Dont just write about your product and its features. Show it! Include screenshots, illustrations, and even video clips of how to use your product.
This will allow your users to get a better feeling of where exactly to click  but also how easy your product actually is  how it was meant to work and be used.
Include direct links
As users use Walkthroughs to learn about your product or service, they will go back and forth between the Walkthrough and the product. It is their reference point, so make it easy for them to go back and forth between the two. Provide direct links, if possible, to the sections you explain.
Address issues or concerns up front
Address the top concerns your users might have when they are trying to decide whether or not to use your product or not. Is it safe, Can I import my data easily?, Can I export my data if I decide to move?. Put any concerns to rest so that your users can start using your product or service with confidence.

---

## Trigger

**URL Validation:** https://ui-patterns.com/patterns/Trigger

### Problem Summary
Place cues on our regular paths to remind and motivate us to take action

### Solution
Spark motivation. In situations where users have the ability, but lack the motivation, increasing motivation is your go-to strategy. Highlighting fear, inspiring hope, or inducing a sense of belonging are well-tested strategies to spark motivation.
	Make hard things easier. In situations where users have a high motivation, but lack ability, facilitating behavior is your weapon of choice. Where training people is hard, costly, and takes time, simplifying tasks is a more effective strategy in leveling required ability with actual ability. A third option is to scale back the ambitions of a target behavior to something smaller. Starting small, first, will provide momentum for something bigger, later.
	Provide a signal. In situations where users have both high motivation and high ability to perform a target behavior, a signal, for instance a simple reminder, is enough. A signal could be a traffic light, request, call to action, a cue, email, tweet, or other distraction.

### Rationale
Without an appropriate prompt, behavior will not occur  even if we are both motivatated and able. Timing is key. When we are ready to perform a behavior, a well-timed trigger is a welcome distraction. A trigger is successfull when we notice it (so we can act on it), when we associate it  with the target behavior, and when it comes at a time where we are both motivated and able to perform the behavior. Triggers can be external (an alarm sounding) or in form of an internal cue (walking through the kitchen triggers opening the fridge).
Triggers cue the user to take action in the context they are in. Triggers might be notifications, tweets, emails, text messages, links, or other distractions. Offline triggers should also be considered. Triggers can be set (alarms), brought home (printed reminder sheet), or follow an action (ask someone a question).

### Usage Examples
Spark motivation. In situations where users have the ability, but lack the motivation, increasing motivation is your go-to strategy. Highlighting fear, inspiring hope, or inducing a sense of belonging are well-tested strategies to spark motivation.
	Make hard things easier. In situations where users have a high motivation, but lack ability, facilitating behavior is your weapon of choice. Where training people is hard, costly, and takes time, simplifying tasks is a more effective strategy in leveling required ability with actual ability. A third option is to scale back the ambitions of a target behavior to something smaller. Starting small, first, will provide momentum for something bigger, later.
	Provide a signal. In situations where users have both high motivation and high ability to perform a target behavior, a signal, for instance a simple reminder, is enough. A signal could be a traffic light, request, call to action, a cue, email, tweet, or other distraction.

---

## Tunnelling

**URL Validation:** https://ui-patterns.com/patterns/Tunnelling

### Problem Summary
Guiding users through a process or experience provides opportunities to persuade along the way

### Solution
Close off detours from the desired behavior without taking away the user’s sense of control. Tunnel users through a decision-making process by removing all unnecessary functions that can possibly distract their attention from completing the process. The tunnel provides opportunity to expose users to information and activities and ultimately to persuasion.
Lead users through a predetermined sequence of actions or events, step by step. When users enter a tunnel, they give up a certain level of self-determination  once they have entered the tunnel, they have committed to experiencing every twist and turn along the way2.
When entering a tunnel, users are exposed to information and activities they might not otherwise have seen or engaged in otherwise. These information and activities provide opportunities for persuasion.

	Ease the process. For users, tunnelinng makes it easier to go through a proess like a workout program, spiritual retreat that controls their daily schedule, or even checking into a drug rehab clinic.
	Control the user experience. For designers, tunneling captures the audience, why they must accept or confront the logic of the controlled environment as content, possible pathways, and the nature of activities that users engage with are predetermined.
	Provide consistency. Tunneling is effective as people value consistency. Once committed to an idea or process, most people tend to stick with it, even in the face of contrary evidence  especially when the tunnel experience was freely chosen by the user.

### Rationale
Tunneling makes it easier to go through a process. For designers, tunneling controls what the user experiences  the content, possible pathways, and the nature of the activities. Tunnels are controlled environments in which users must accept the assumptions, values, and logic inflicted upon them.
Tunneling is effective as we value consistency. Once users commit to an idea or a process, most tend to stick with it. This is especially true in a tunnel situations that have been freely chosen2.

### Usage Examples
Close off detours from the desired behavior without taking away the user’s sense of control. Tunnel users through a decision-making process by removing all unnecessary functions that can possibly distract their attention from completing the process. The tunnel provides opportunity to expose users to information and activities and ultimately to persuasion.
Lead users through a predetermined sequence of actions or events, step by step. When users enter a tunnel, they give up a certain level of self-determination  once they have entered the tunnel, they have committed to experiencing every twist and turn along the way2.
When entering a tunnel, users are exposed to information and activities they might not otherwise have seen or engaged in otherwise. These information and activities provide opportunities for persuasion.

	Ease the process. For users, tunnelinng makes it easier to go through a proess like a workout program, spiritual retreat that controls their daily schedule, or even checking into a drug rehab clinic.
	Control the user experience. For designers, tunneling captures the audience, why they must accept or confront the logic of the controlled environment as content, possible pathways, and the nature of activities that users engage with are predetermined.
	Provide consistency. Tunneling is effective as people value consistency. Once committed to an idea or process, most people tend to stick with it, even in the face of contrary evidence  especially when the tunnel experience was freely chosen by the user.

---

## Unlock Features

**URL Validation:** https://ui-patterns.com/patterns/Unlock-features

### Problem Summary
Utilize a user’s desire to explore by unlocking new features as a reward for specific behaviors

### Solution
Reward contributors and curators for their good deeds as they add content to your system. Unlocked powers act as endowments that will lock your users into valuing your website more than before they signed up. In a social website setting, show off users with unlocked features to give rookies something to strive for.
Unlock features for your users as they explore and engage your system. The principle of unlocking features is widespread in computer games, where users are rewarded by being moved to new parts of the game (access to a new level, win a key to a locked door, etc.) upon achieving something specific. In web design, it is most often the contributor and curator role that is being rewarded as their activity is what makes or brakes a social website.
The relationship between the contributors and curators are often intertwined in that users with a proven track record of quality content are immediately promoted more than a rookie user or a user with a poor track record.
You can choose to either have a fixed currency for unlocking features (points) or unlock features as users reach specifically set goals.

	Reward good deeds. Reward contributors and curators for their good deeds as they add content to your system.
	Provide appropriate challenges. Dole out appropriate tools and challenges as the skill level of users increase with their continued use. An advanced feature might be too much to handle for a novice and can be liberating for an expert user to get access to.
	Lock in users to your product. Unlocked capabilities act as endowments that will lock your users into valuing your website more than before they signed up. In a social website setting, show off users with unlocked features to give rookies something to strive for.

Example: Karma points at Hacker News
On Hacker News, users unlock features as they collect karma points. Karma points are earned for a popular post, successful curated content and the likes. The amount of points needed for certain features is victim for constant scrutiny and adjustment, as it has a clear connection to the quality and amount of contributions of the site. At some point, these were the karma point limits of unlocking features:

	10 karma  Upvote comments
	51 karma  Downvote comments
	51 karma  Flag comments
	200 karma  Make polls
	250 karma  Customize the top bar background color

Points are an effective way to communicate a clear one-way path up the status ladder. Its also a great to keep score of users deeds. There are however other ways of quantifying the criteria for unlocking features.
Other ways of quantifying the criteria for unlocking features
You do not need to have a point system up and running in order to clearly communicate the path to unlocking features. Another take is to unlock features based on what type the user is. If a user is typically a commenter and active in that field, then unlock flagging and rating comments once the user has commented 20 times. If a user is contributing a lot of uploads, then unlock power rating on just uploads after 10 submissions.
Other unlock goals could be to recruit friends to join the website or share a link.

### Rationale
As your users get accustomed to your product, their skill level rises and what was first a challenging task becomes tedious. To match the growing skill level of your users and avoid boredom as users evolve from novice to expert users, unlocking more advanced features is a common strategy.
As users explore your website and start unlocking features, they invest time and effort into your website. The effects of Loss aversion and the Endowment effect will lock your users in to valuing your website more than before they signed up. The points and features you have earned are valued more when their value is judged as a loss than a gain. Points already earned are valued more than points to be earned. The status and history of having achieved a large set of features will lock in users to sticking with your site.
Furthermore, the higher status you have in a community and the more power you have with the features you unlock, the more Social proof there is that you are to be trusted. This social proof has been utilized by google, who is known to have invited job candidates based on users stackoverflow.com accounts.

### Usage Examples
Reward contributors and curators for their good deeds as they add content to your system. Unlocked powers act as endowments that will lock your users into valuing your website more than before they signed up. In a social website setting, show off users with unlocked features to give rookies something to strive for.
Unlock features for your users as they explore and engage your system. The principle of unlocking features is widespread in computer games, where users are rewarded by being moved to new parts of the game (access to a new level, win a key to a locked door, etc.) upon achieving something specific. In web design, it is most often the contributor and curator role that is being rewarded as their activity is what makes or brakes a social website.
The relationship between the contributors and curators are often intertwined in that users with a proven track record of quality content are immediately promoted more than a rookie user or a user with a poor track record.
You can choose to either have a fixed currency for unlocking features (points) or unlock features as users reach specifically set goals.

	Reward good deeds. Reward contributors and curators for their good deeds as they add content to your system.
	Provide appropriate challenges. Dole out appropriate tools and challenges as the skill level of users increase with their continued use. An advanced feature might be too much to handle for a novice and can be liberating for an expert user to get access to.
	Lock in users to your product. Unlocked capabilities act as endowments that will lock your users into valuing your website more than before they signed up. In a social website setting, show off users with unlocked features to give rookies something to strive for.

Example: Karma points at Hacker News
On Hacker News, users unlock features as they collect karma points. Karma points are earned for a popular post, successful curated content and the likes. The amount of points needed for certain features is victim for constant scrutiny and adjustment, as it has a clear connection to the quality and amount of contributions of the site. At some point, these were the karma point limits of unlocking features:

	10 karma  Upvote comments
	51 karma  Downvote comments
	51 karma  Flag comments
	200 karma  Make polls
	250 karma  Customize the top bar background color

Points are an effective way to communicate a clear one-way path up the status ladder. Its also a great to keep score of users deeds. There are however other ways of quantifying the criteria for unlocking features.
Other ways of quantifying the criteria for unlocking features
You do not need to have a point system up and running in order to clearly communicate the path to unlocking features. Another take is to unlock features based on what type the user is. If a user is typically a commenter and active in that field, then unlock flagging and rating comments once the user has commented 20 times. If a user is contributing a lot of uploads, then unlock power rating on just uploads after 10 submissions.
Other unlock goals could be to recruit friends to join the website or share a link.

---

## Value Attribution

**URL Validation:** https://ui-patterns.com/patterns/Value-attribution

### Problem Summary
The perceived value of things increases with their cost and appearance

### Solution
We tend to attribute the value, goodness, or authenticity of something to its context instead of the thing itself

	Stand out. Consider positioning core traits of your product to significantly stand out from the competition to increase the perceived value of your product. It could be with a much higher price (or price one plan of many higher to let it act as a decoy), remarkablel brand, or acting with attitudes contrary to the established market.
	Invested time as cost. Consider whether you can get users to invest their time in your product before paying to use it. This might increase its perceived monetary value.
	Attribution decays. The perceived value we infer from value attribution decays over time as we both have time to compare and contrast with more evidence. A conversion to sale is most likely to happen as the value attribution is assigned.

### Rationale
We tend to assign unobservable traits to people and things based on its context and a few predominant cues rather than objective data. A high price may induce perceived qualities not seen if priced lower. An attractive appearance may infer a perception that a product works better. As we evaluate the value and traits of a product, cues like price, brand, appearance, and behavior have significant influence.

### Usage Examples
We tend to attribute the value, goodness, or authenticity of something to its context instead of the thing itself

	Stand out. Consider positioning core traits of your product to significantly stand out from the competition to increase the perceived value of your product. It could be with a much higher price (or price one plan of many higher to let it act as a decoy), remarkablel brand, or acting with attitudes contrary to the established market.
	Invested time as cost. Consider whether you can get users to invest their time in your product before paying to use it. This might increase its perceived monetary value.
	Attribution decays. The perceived value we infer from value attribution decays over time as we both have time to compare and contrast with more evidence. A conversion to sale is most likely to happen as the value attribution is assigned.

---

## Variable Rewards

**URL Validation:** https://ui-patterns.com/patterns/Variable-rewards

### Problem Summary
Use random rewards to convey a sense of scarcity and unpredictability to entice users curiosity in discovering the pattern

### Solution
The activity level of users is a function of how soon they expect a reward to be given. The more certain they are that something good or interesting will happen soon, the more activity they will produce. When users know a reward is a long way off, the motivation is low and so is user activity2. This reward schedule is called a fixed one, as users are rewarded again and again with a fixed ratio or interval. Variable ratios and intervals on the other hand randomize rewards around an average. The latter produce the highest activity in users.

	Avoid extinction. As you stop providing a recurring reward the sudden lack will likely feel as punishment and cause anger and frustration.
	Find the right balance. Are rewards building up too fast, too slow, or just right? If the user can’t catch up, he or she will become satiated, and the reinforced behavior will go to extinction. Record awards provided, and observe the effect to strike the right balance. Balancing rewards is often a question of “good enough”.
	Facilitate intrinsic rewards. Motivation coming from an pleasure of the activity itself is stronger and more sustainable than motivation coming from extrinsic rewards (although easier to administer). This is why it makes sense to use the extrinsic motivation from rewards to facilitate behavior that will lead to intrinsic rewards such as mastery, recognition, and personal growth.

Read on to find out what variable reward ratios are and how they are different to fixed ratios and intervals.
Example: Lomography.com
Lomography.com sells retro analogue cameras on their website and in physical stores. To spark the enthusiasm of their lomographic society (fans taking pictures with lomography cameras), Lomography has created an online community for sharing pictures.
Community activity is backed by a piggie bank system where users can earn piggie points by having their photos selected as photo of the day, by submitting reviews of cameras and accessories, by winning rumbles and competitions, by translating content, and much more. Piggie points, which have an expiration date, can be used in the online shop to by cameras and thus translate into cold cash. The piggie bank system utilizes a mix of fixed and variables ratios and intervals.
At the retro camera company, Lomography, you can earn piggie points for your online activity, which translates to cold cash in the lomography online store. Piggy point rewards are given out both at fixed ratios and at variable intervals.

### Rationale
As humans, and animals, we react differently to certain patterns of rewards. Behaviorism has studied these patterns2 and have come to the conclusion that variable reward schedules and contingencies motivate us more than fixed schedules and contingencies.
Contingencies are rules or sets of rules defining when rewards are given out. There are two fundamental sort of contingencies: ratios and intervals. Ratios schedules provide a reward after a certain amount of actions have been carried out  the more you do, the more you get. Interval schedules provide a reward after a certain amount of time has passed.
Fixed vs variable ratios
Rewards with a fixed ratio are given out again and again after completing the same action the same amount of times. It could be that you will receive 10 karma points every 5th time you reply to a comment or that you would increase your level every 10th time you uploaded a video.
The problem with fixed ratios is that users distinctly pause completing actions when they receive a reward, as they know receiving a new reward will take a while. This creates an opportune moment for the user to walk away. However, the break in rewards caused by fixed reward ratios might also give the user an opportunity to explore different aspects the system.
Variable ratios are rewarded after a specific number of actions have been carried out, but that number changes every time. A user might know to upload approximately 10 videos to rise in levels, but the precise number is randomly generated every time  everything has a chance of reward. Such variable ratios have proven to stimulate more activity than fixed ratios  even when on average the same amount of rewards are given out.
Variable ratios are free from the pause in activity generated from fixed ratios. Its important to note that users do not know how many actions are required this time, just the average number from previous experience2.
Rewarding with fixed ratios produces a pause in activity after a reward has been given and a burst of activity just before being rewarded. While users typically respond at a higher rate in the fixed ratios bursts, variable reward ratios provide a more consistent rate free from pauses of the fixed ratios.
Fixed vs variable intervals
Instead of providing a reward after a certain number of actions has been completed, interval schedules provide rewards after a certain amount of time has passed. Users being rewarded in fixed intervals will pause activity once an award has been given and wander around for a while. They will return frequently to check if their reward has been refilled or has reappeared. Gradually, checks will become more frequent as the proper time nears.
Vimeo.com utilizes fixed reward intervals for its regular users, who are allowed to upload only 500 mb of video every week. After the fixed interval of one week, the users upload quota is refilled. As users reach their upload quota on vimeo.com, their activity will pause until its refilled next week. Vimeo hopes users will use the pause to consider buying a pro account with no upload quota.
With variable reward intervals, the period of time changes after each reward as with the variable ratios. As with variable ratios, variable intervals also produce a steady and continuous flow of activity  there is always a reason to be active.

### Usage Examples
The activity level of users is a function of how soon they expect a reward to be given. The more certain they are that something good or interesting will happen soon, the more activity they will produce. When users know a reward is a long way off, the motivation is low and so is user activity2. This reward schedule is called a fixed one, as users are rewarded again and again with a fixed ratio or interval. Variable ratios and intervals on the other hand randomize rewards around an average. The latter produce the highest activity in users.

	Avoid extinction. As you stop providing a recurring reward the sudden lack will likely feel as punishment and cause anger and frustration.
	Find the right balance. Are rewards building up too fast, too slow, or just right? If the user can’t catch up, he or she will become satiated, and the reinforced behavior will go to extinction. Record awards provided, and observe the effect to strike the right balance. Balancing rewards is often a question of “good enough”.
	Facilitate intrinsic rewards. Motivation coming from an pleasure of the activity itself is stronger and more sustainable than motivation coming from extrinsic rewards (although easier to administer). This is why it makes sense to use the extrinsic motivation from rewards to facilitate behavior that will lead to intrinsic rewards such as mastery, recognition, and personal growth.

Read on to find out what variable reward ratios are and how they are different to fixed ratios and intervals.
Example: Lomography.com
Lomography.com sells retro analogue cameras on their website and in physical stores. To spark the enthusiasm of their lomographic society (fans taking pictures with lomography cameras), Lomography has created an online community for sharing pictures.
Community activity is backed by a piggie bank system where users can earn piggie points by having their photos selected as photo of the day, by submitting reviews of cameras and accessories, by winning rumbles and competitions, by translating content, and much more. Piggie points, which have an expiration date, can be used in the online shop to by cameras and thus translate into cold cash. The piggie bank system utilizes a mix of fixed and variables ratios and intervals.
At the retro camera company, Lomography, you can earn piggie points for your online activity, which translates to cold cash in the lomography online store. Piggy point rewards are given out both at fixed ratios and at variable intervals.

---

## Vertical Dropdown Menu

**URL Validation:** https://ui-patterns.com/patterns/VerticalDropdownMenu

### Problem Summary
The user needs to navigate among sections of a website, but space to show such navigation is limited.

### Solution
A list of main sections is listed on the same horizontal line. Once the user has his mouse cursor over one of the list items, a drop-down list of new options is shown below the list item the mouse cursor is pointing at. The user can then follow the now vertically extended list item down, to select the menu item he wants to click.
Once the user removes the cursor from the box of drop-downed options, the box disappears. He can then put his mouse cursor over another list item, whereafter the process starts over.
As humans, we do not always act perfectly as the system would like us to. To cope with human errors and to guide us to act as you would like us to, you can implement the following:

	On mouseout events (when the user takes his mouse away from the drop-downed box), add a delay before hiding the drop-downed box (typically 200-300 ms.)
	Make the area of each menu item wider than just the text of the menu item so that the user has more space to put his mouse cursor over.
	Change the cursor image as the user hovers over a list item.

Other issues you want to take notice of:
There are many different kind of drop-down menus out there. Some work only  and is built purely with javascript. These kinds of drop-down menus do not work well with search engines. To let the search engines index your page, you would want to have the menu formatted in HTML from the beginning of the page load, rather than building it in javascipt client-side after the page has loaded.

### Rationale
Drop-down menus save space. This is the main reason for using them. Otherwise, drop-down menus are not regarded as a technique that increases usability, as they can often be difficult to use.
Flyout menus allow for only showing top levels of the pages hierarchy permanently, while still giving the option to show deeper levels on mouse over.

### Usage Examples
A list of main sections is listed on the same horizontal line. Once the user has his mouse cursor over one of the list items, a drop-down list of new options is shown below the list item the mouse cursor is pointing at. The user can then follow the now vertically extended list item down, to select the menu item he wants to click.
Once the user removes the cursor from the box of drop-downed options, the box disappears. He can then put his mouse cursor over another list item, whereafter the process starts over.
As humans, we do not always act perfectly as the system would like us to. To cope with human errors and to guide us to act as you would like us to, you can implement the following:

	On mouseout events (when the user takes his mouse away from the drop-downed box), add a delay before hiding the drop-downed box (typically 200-300 ms.)
	Make the area of each menu item wider than just the text of the menu item so that the user has more space to put his mouse cursor over.
	Change the cursor image as the user hovers over a list item.

Other issues you want to take notice of:
There are many different kind of drop-down menus out there. Some work only  and is built purely with javascript. These kinds of drop-down menus do not work well with search engines. To let the search engines index your page, you would want to have the menu formatted in HTML from the beginning of the page load, rather than building it in javascipt client-side after the page has loaded.

---

## Vote To Promote

**URL Validation:** https://ui-patterns.com/patterns/VoteToPromote

### Problem Summary
The user wants to promote a specific piece of content in order to democratically help decide what content is more popular.

### Solution
Let users participate in content curation by letting them promote quality content.
Use the power of your community to help curate what is more popular. Display a voting mechanism next to each candidate item. As users click, their vote is counted in favor of promoting that item. Consider providing an embeddable and stand-alone voting mechanism that third-party publishers can include on their site.
4 Mechanisms working together
This pattern consists of a number of mechanisms that work together:

	Voting mechanism. Provide a mechanism whereby users can vote for or against each item of content on your website.  A user gets one vote and can change that vote at a later time. When a user casts a vote on an item, this information should be provided back to the user as feedback. Let the user see his or her prior votes and in some cases allow the user to change those votes.
	Display number of votes an item has received. This will give your visitors a clear indication of how popular an item is and allow for comparison with other items.
	Sum up popular items. Provide lists of popular content summed up on a main page.
	Favor popular items. Favor popular items in search results, when browsing tags, and showing related information.
	Content submission mechanism. You can let users submit content in several ways.

Let users submit
Provide a webpage with a submission form. The most basic and traditional way to let your users submit content is via a form on a webpage that you host. After content has been submitted, your users can freely vote on the submitted contents quality.
Make voting embeddable
Provide a widget for the user to  to place on his or her website. If the type of content your users are submitting, you can provide a widget to your users to place on their own website. This will allow third-party publishers to submit content directly from their own website. The widget is really a javascript include code, that will add the address of the webpage, if the webpage has not been added to your site yet.

### Rationale
The Vote To Promote pattern promotes community participation and can potentially help pick up and promote the newest and hottest content around. By using your community to judge what is more popular, you avoid the need to hire paid professional reviewers.

### Usage Examples
Let users participate in content curation by letting them promote quality content.
Use the power of your community to help curate what is more popular. Display a voting mechanism next to each candidate item. As users click, their vote is counted in favor of promoting that item. Consider providing an embeddable and stand-alone voting mechanism that third-party publishers can include on their site.
4 Mechanisms working together
This pattern consists of a number of mechanisms that work together:

	Voting mechanism. Provide a mechanism whereby users can vote for or against each item of content on your website.  A user gets one vote and can change that vote at a later time. When a user casts a vote on an item, this information should be provided back to the user as feedback. Let the user see his or her prior votes and in some cases allow the user to change those votes.
	Display number of votes an item has received. This will give your visitors a clear indication of how popular an item is and allow for comparison with other items.
	Sum up popular items. Provide lists of popular content summed up on a main page.
	Favor popular items. Favor popular items in search results, when browsing tags, and showing related information.
	Content submission mechanism. You can let users submit content in several ways.

Let users submit
Provide a webpage with a submission form. The most basic and traditional way to let your users submit content is via a form on a webpage that you host. After content has been submitted, your users can freely vote on the submitted contents quality.
Make voting embeddable
Provide a widget for the user to  to place on his or her website. If the type of content your users are submitting, you can provide a widget to your users to place on their own website. This will allow third-party publishers to submit content directly from their own website. The widget is really a javascript include code, that will add the address of the webpage, if the webpage has not been added to your site yet.

---

## WYSIWYG

**URL Validation:** https://ui-patterns.com/patterns/WYSIWYG

### Problem Summary
The user wants to create content that contains rich media and formatted text but does not the knowledge or time to write HTML.

### Solution
There are many javascript libraries available online that will convert a textarea/ HTML element into a fully functioning WYSIWYG editor. The editor displays a work area that is both input and the final formatted output. The content is stored as HTML in a database.
Editors can be customized to your user’s needs. You can disable unnecessary functions. You might choose to not allow image inserts, tampering with font color or size – or even force the user to only use a predefined list of CSS classes.

### Rationale
WYSIWYG (What You See Is What You Get) was initially introduced in word processors such as WordPerfect and Microsoft Word. It was then a revolutionary way to write documents, where the editor on the screen mimicked the result in print.
Recently, WYSIWYG editors were introduced to forms on the web. Previously, long text was inserted into textarea/ fields, with no formatting options what-so-ever. WYSIWYG editors now allow the input to mimic what will be seen on screen.

### Usage Examples
There are many javascript libraries available online that will convert a textarea/ HTML element into a fully functioning WYSIWYG editor. The editor displays a work area that is both input and the final formatted output. The content is stored as HTML in a database.
Editors can be customized to your user’s needs. You can disable unnecessary functions. You might choose to not allow image inserts, tampering with font color or size – or even force the user to only use a predefined list of CSS classes.

---

## Wiki

**URL Validation:** https://ui-patterns.com/patterns/Wiki

### Problem Summary
You want to create a repository for your website or application where users can produce and manage information while collaborating on public content.

### Solution
A wiki is a page concept itself, and not just a pattern that functions as a part of a website. The format however represents enough value in itself to represent a design pattern and not just a page concept.
A wiki page can be edited by anyone. Anyone can modify information and add new pages to the document collection. All pages are under version control, and can easily be rolled back to earlier versions. A wiki allows users to easily create, edit and link web pages together.
A wiki enables documents to be written collaboratively, in a simple markup language using a web browser. A single page in a wiki is referred to as a wiki page, while the entire body of pages, which are usually highly interconnected via hyperlinks, is the wiki. A wiki is essentially a database for creating, browsing and searching information. [Wikipedia.org]

### Rationale
Wikis are often used to create collaborative websites, power community websites, and are increasingly being installed by businesses to provide affordable and effective Intranets or for use in Knowledge Management. [Wikipedia.org]

### Usage Examples
A wiki is a page concept itself, and not just a pattern that functions as a part of a website. The format however represents enough value in itself to represent a design pattern and not just a page concept.
A wiki page can be edited by anyone. Anyone can modify information and add new pages to the document collection. All pages are under version control, and can easily be rolled back to earlier versions. A wiki allows users to easily create, edit and link web pages together.
A wiki enables documents to be written collaboratively, in a simple markup language using a web browser. A single page in a wiki is referred to as a wiki page, while the entire body of pages, which are usually highly interconnected via hyperlinks, is the wiki. A wiki is essentially a database for creating, browsing and searching information. [Wikipedia.org]

---

## Wizard

**URL Validation:** https://ui-patterns.com/patterns/Wizard

### Problem Summary
The user wants to achieve a single goal which can be broken down into dependable sub-tasks.

### Solution
Break down a single goal into dependable sub-tasks.
The task of inputting data into the system is parted into multiple steps. Each step is presented to the user one at a time.
The user should be presented with information about the steps that exist, progress through the process and which steps are completed.
The Wizard pattern is very similar to the Steps Left pattern. The difference between the two is the focus. Where Steps Left is focused only on explaining the steps of a process, the Wizard pattern is about parting dependable sub-tasks needed to perform a complex goal into separate steps.
The Wizard pattern is also different from the Steps Left pattern in that the steps needed to perform a goal can vary depending on the information inputted in earlier stages. In this way, the Wizard pattern separates itself from being merely an visible aid for the user.
Buttons
Basically, a wizard is a series of screens or dialogue boxes walking users through from start to completion. Each screen asks the user to input information by either making selections or filling in fields. After inputting data, users navigate through the wizard by clicking navigation options like Previous and Next. At the final step users click Finish instead of Next, which thus indicates the completion of the wizard.
It is also good practice to include a Cancel button on all screens that will lead the user back to where he or she came from. Typically, a Cancel button is located near other navigation buttons, but in a position that clearly separates the button from the Previous and Next buttons. Furthermore, it is also good practice to provide a warning if data inputted up to that point will be lost clicking the Cancel button. It is fair for to assume that the user expects that he or she can return to the wizard later and start from where they left off3. In order not to frustrate the user more than necessary, the consequences of exiting the wizard should be communicated.
Wizards are meant to be fast and easy. For this reason, it is a good idea to keep the content of a screen as well as its navigation above the fold.
Keep the purpose clear: explain
Keep the wizards purpose clear on every screen by placing a clear and concise label on every screen. Optionally accompany the label with a brief explanation of the wizards purpose on the first screen. This will help users remember why they entered the wizard in the first place and how they will benefit from finishing the wizard.
Use plain language
Users of a wizard arent necessarily experts, why you should refrain from using technical jargon to prompt users. The language used should fit in to the users frame of reference5.
Summarize choices
It is good practice to present a summary of choices made throughout the wizard to the user near the end of the wizard. This will allow the user to review and double-check inputted data before the final Finish button is clicked. In the case the user wishes to change the data entered, he or she should be able to navigate back to the given page where the date was entered. If the amount of steps in the wizard is greater than 8-10, it is a good idea to provide links directly to the screen of the data input.
Good defaults
A wizard is a perfect place for using Good defaults. Most wizard users are not familiar with the task they are performing and are thus unfamiliar with the values for the choices they are asked to make.

### Rationale
By splitting up a complex task into a sequence of chunks, you can effectively simplify the task. Each chunk represents a separate mental space, easier to deal with alone than as a whole. Contrary to the Steps Left pattern, the steps needed to perform a goal can vary depending on the information inputted in earlier stages.
By separating complex tasks needed to achieve a goal into several steps, the process of inputting data can take several different directions depending on what input is entered.
The complex task of inputting large amounts of dependable data can be adjusted and streamlined to fit the decisions of a user throughout a process. In the context of decisions the user makes in each step, unnecessary steps can be cut out and important steps can enter into the focus.
In a system with many variables, a user can reach their  goals by manipulating these variables in different ways. The Wizard pattern can be used to group such variables into separate goals. This will convert the task of completing a complex goal from multiple disparate actions into a coherent process.
When users are forced to follow a set of pre-defined steps they are less likely to miss important aspects of a process and will thus commit fewer errors.
Minimum of training
Wizards are often made for the untrained user. For this reason, make sure your wizard can be completed without training. A rationale behind using a wizard is to avoid training for rare or intimidating tasks  not to develop expertise5.

### Usage Examples
Break down a single goal into dependable sub-tasks.
The task of inputting data into the system is parted into multiple steps. Each step is presented to the user one at a time.
The user should be presented with information about the steps that exist, progress through the process and which steps are completed.
The Wizard pattern is very similar to the Steps Left pattern. The difference between the two is the focus. Where Steps Left is focused only on explaining the steps of a process, the Wizard pattern is about parting dependable sub-tasks needed to perform a complex goal into separate steps.
The Wizard pattern is also different from the Steps Left pattern in that the steps needed to perform a goal can vary depending on the information inputted in earlier stages. In this way, the Wizard pattern separates itself from being merely an visible aid for the user.
Buttons
Basically, a wizard is a series of screens or dialogue boxes walking users through from start to completion. Each screen asks the user to input information by either making selections or filling in fields. After inputting data, users navigate through the wizard by clicking navigation options like Previous and Next. At the final step users click Finish instead of Next, which thus indicates the completion of the wizard.
It is also good practice to include a Cancel button on all screens that will lead the user back to where he or she came from. Typically, a Cancel button is located near other navigation buttons, but in a position that clearly separates the button from the Previous and Next buttons. Furthermore, it is also good practice to provide a warning if data inputted up to that point will be lost clicking the Cancel button. It is fair for to assume that the user expects that he or she can return to the wizard later and start from where they left off3. In order not to frustrate the user more than necessary, the consequences of exiting the wizard should be communicated.
Wizards are meant to be fast and easy. For this reason, it is a good idea to keep the content of a screen as well as its navigation above the fold.
Keep the purpose clear: explain
Keep the wizards purpose clear on every screen by placing a clear and concise label on every screen. Optionally accompany the label with a brief explanation of the wizards purpose on the first screen. This will help users remember why they entered the wizard in the first place and how they will benefit from finishing the wizard.
Use plain language
Users of a wizard arent necessarily experts, why you should refrain from using technical jargon to prompt users. The language used should fit in to the users frame of reference5.
Summarize choices
It is good practice to present a summary of choices made throughout the wizard to the user near the end of the wizard. This will allow the user to review and double-check inputted data before the final Finish button is clicked. In the case the user wishes to change the data entered, he or she should be able to navigate back to the given page where the date was entered. If the amount of steps in the wizard is greater than 8-10, it is a good idea to provide links directly to the screen of the data input.
Good defaults
A wizard is a perfect place for using Good defaults. Most wizard users are not familiar with the task they are performing and are thus unfamiliar with the values for the choices they are asked to make.

---

## Appointment Dynamic

**URL Validation:** https://ui-patterns.com/patterns/appointment-dynamic

### Problem Summary
Force users to return at a set time to take a specific action and claim a reward

### Solution
Reward those who return and punish those who fail to re-engage on time.

	Create traditions. Let the time and place to come back recur over fixed time schedules, i.e. every Tuesday, first day of the month, or similar. This will make it easier to remember and commit to  especially for groups and social contexts. Happy hour is a great example.
	Penalize no-shows. Make it clear that not showing up at the set time will have negative consequences, just as showing up will have positive ones. In the game Farmville, your crops will vanish upon inaction.
	Set a new appointment. Once the user comes back, make sure that it is very explicit when they need to be back again, before leaving.

### Rationale
The appointment dynamic provides reason and immediacy for the user to come back. Making the action required- and the window to take the action explicit can help create a sense of urgency as it becomes clear when the reward will be harvested or missed. Appointment dynamics are often tied to reward schedules that motivate frequent action.

### Usage Examples
Reward those who return and punish those who fail to re-engage on time.

	Create traditions. Let the time and place to come back recur over fixed time schedules, i.e. every Tuesday, first day of the month, or similar. This will make it easier to remember and commit to  especially for groups and social contexts. Happy hour is a great example.
	Penalize no-shows. Make it clear that not showing up at the set time will have negative consequences, just as showing up will have positive ones. In the game Farmville, your crops will vanish upon inaction.
	Set a new appointment. Once the user comes back, make sure that it is very explicit when they need to be back again, before leaving.

---

## Auto-sharing

**URL Validation:** https://ui-patterns.com/patterns/auto-sharing

### Problem Summary
The user wants to easily share their activity with their social networks.

### Solution
Lets Allow users to quickly and easily share particular interactions with their social networks. Web applications like Tumblr, Spotify and Vimeo all have granular sharing settings, which allow users to automatically post updates to their networks based on their activity. These updates can be posted within the application or even shared with external social channels like Facebook or Twitter.

### Rationale
Auto-sharing help users engage with their friends and family in everyday activities like listening to a song or reading an article on an external website.
Furthermore, auto-sharing is a great way to build awareness and engagement within the application itself. For interactions like uploading a photo to Carousel or a video to Vimeo, this pattern makes it even easier for users by eliminating an extra step in the process which they are most likely going to take.

### Usage Examples
Lets Allow users to quickly and easily share particular interactions with their social networks. Web applications like Tumblr, Spotify and Vimeo all have granular sharing settings, which allow users to automatically post updates to their networks based on their activity. These updates can be posted within the application or even shared with external social channels like Facebook or Twitter.

---

## Autonomy

**URL Validation:** https://ui-patterns.com/patterns/autonomy

### Problem Summary
We strive to feel in control

### Solution
Speed up interactions. Speeding up interactions can help users feel more in control. Provide instant feedback as the user interacts with an interface to keep his or her momentum. Measures to speed up interactions could be to split up tasks and attention and reduce complexity.
	Allow customization. Adjusting our environment to our preferences, competence, and flow can provide a sense of freedom. Consider allowing customization of UI color, personal shortcuts, favorites, etc.
	Provide a sense of meaning. Meaning, competence, power to influence, and emotional engagement add to the feeling of autonomy and in turn satisfaction.
	Allow escape. Users might choose paths by mistake or regret embarking on it half-way. Provide a clearly marked emergency exit to leave the unwanted state without having to go through an extended dialogue. Support undo and redo.

### Rationale
A perception of greater autonomy increases the feeling of certainty and reduces stress. We are intrinsically motivatetd to satisfy our need for autonomy and report a higher state of well-being when met. Give people the freedom to make choices that align with their priorities and values rather than forcing them through a predefined path.

### Usage Examples
Speed up interactions. Speeding up interactions can help users feel more in control. Provide instant feedback as the user interacts with an interface to keep his or her momentum. Measures to speed up interactions could be to split up tasks and attention and reduce complexity.
	Allow customization. Adjusting our environment to our preferences, competence, and flow can provide a sense of freedom. Consider allowing customization of UI color, personal shortcuts, favorites, etc.
	Provide a sense of meaning. Meaning, competence, power to influence, and emotional engagement add to the feeling of autonomy and in turn satisfaction.
	Allow escape. Users might choose paths by mistake or regret embarking on it half-way. Provide a clearly marked emergency exit to leave the unwanted state without having to go through an extended dialogue. Support undo and redo.

---

## Autosave

**URL Validation:** https://ui-patterns.com/patterns/autosave

### Problem Summary
The user wants to keep their data safe and saved while focusing on working without having to remember to do so.

### Solution
Prevent accidental data loss by automatically saving user input at fixed intervals or at events of interest.
Consider at what frequency it makes sense to auto-save inputted content for your application, and at what events it makes sense to trigger an auto-save. The most obvious event is clicking the save-button, but the event of moving the focus to another field might also be interesting to observe.
The save button
To better guide users as to what state their document is in, consider changing the label of the save button from Save, when the form contains uncommited changes to Saved when the current form represents what has been saved in storage.

### Rationale
Let users worry about creating great content rather than about loosing it. Removing the save button entirely can create fear, so consider keeping it around to make users feel safe. Leave an unobtrusive trace of conducted user actions and consider complementing with the Undo pattern.

### Usage Examples
Prevent accidental data loss by automatically saving user input at fixed intervals or at events of interest.
Consider at what frequency it makes sense to auto-save inputted content for your application, and at what events it makes sense to trigger an auto-save. The most obvious event is clicking the save-button, but the event of moving the focus to another field might also be interesting to observe.
The save button
To better guide users as to what state their document is in, consider changing the label of the save button from Save, when the form contains uncommited changes to Saved when the current form represents what has been saved in storage.

---

## Cards

**URL Validation:** https://ui-patterns.com/patterns/cards

### Problem Summary
The user needs to browse content of varying types and length

### Solution
Display entry points to detailed and varied content in similar shapes. A card could contain a photo, text, and a link about a single subject.
Consider only scrolling collections of cards in one direction: horizontally or vertically. Card content that exceeds the maximum card height (if scrolling vertically) or width (if scrolling horizontally) is truncated and does not scroll, but can be expanded. Once expanded, a card may exceed the maximum height/width of the view.
A card typically includes a few different types of media, such as an image, a title, a short summary and a call-to-action button.
Cards can be manipulated
One of the most important things about cards, is their ability to be manipulated almost infinitely.  They can be turned over to reveal more, stacked to save space, folded for a summary  and expanded for more details, sorted, and grouped.
We can hint what is on the back side or that the card can be folded out. The resemblance of Cards to the physical world makes them a great conceptual metaphor for which we can easily relate all sorts of manipulations.

### Rationale
Browsing is a large part of interaction, and users want to be able to quickly scan large portions of content and dive deep into their interests. Users can experience difficulty browsing text-heavy sites as displaying extra details for each item can clutter the screen and prevent efficient scanning.
Cards are great for showcasing aggregated elements whose size or supported actions vary. Each card serves as an entry point to more detailed information, so it shouldnt be overloaded with extraneous information or actions. They are dismissible, swipeable, sortable, and filterable.
Cards allow you to present a heavy dose of content in a small and digestible manner: they divide all available content into meaningful sections, present a summary and link to additional details. A single card is a container that displays various parts of related information, from which users can get even more information.
Why use cards?
Cards help chunk data into content that is more easily aids scanned. Furthermore, cards are:

	Intuitive. Cards look similar to real-world tangible cards as they appear in user interfaces. They seem familiar to users. Before cards became popular elements in mobile and web apps, they were all around in real life: business cards, baseball cards, sticky notes. Cards represent a helpful visual metaphor that allow our brains to intuitively connect a card with the piece of content it represents – just like in real life.
	Easy to digest. Cards dont take up much space and forces the designer to prioritise its content and form. In turn, each card becomes digestible pieces of content that are easily accessed and scanned. Cards make it easier for users to find the content that they are interested in  in turn this empowers them to engage in any way they want.
	Cards are attractive. Card-based design often relies heavily on visuals (especially, images); any copy is usually secondary to the visual in terms of the information architecture. The emphasis on using images can help make card-based design more attractive to users than the same content not arranged in cards.
	Advantageous for responsive design. Cards are almost infinitely manipulatable: the rectangular shape resizes smoothly to fit the horizontal and vertical orientations of different screens (easily scale up or down), which means users get a consistent experience across all devices.
	Shareable. Cards can encourage users to share content on social media, as it allows users to easily share only specific chunk of content vs a whole page.

### Usage Examples
Display entry points to detailed and varied content in similar shapes. A card could contain a photo, text, and a link about a single subject.
Consider only scrolling collections of cards in one direction: horizontally or vertically. Card content that exceeds the maximum card height (if scrolling vertically) or width (if scrolling horizontally) is truncated and does not scroll, but can be expanded. Once expanded, a card may exceed the maximum height/width of the view.
A card typically includes a few different types of media, such as an image, a title, a short summary and a call-to-action button.
Cards can be manipulated
One of the most important things about cards, is their ability to be manipulated almost infinitely.  They can be turned over to reveal more, stacked to save space, folded for a summary  and expanded for more details, sorted, and grouped.
We can hint what is on the back side or that the card can be folded out. The resemblance of Cards to the physical world makes them a great conceptual metaphor for which we can easily relate all sorts of manipulations.

---

## Cashless Effect

**URL Validation:** https://ui-patterns.com/patterns/cashless-effect

### Problem Summary
We spend more when no cash is involved in a transaction

### Solution
Less friction results in more sales. Make paying effortless. The less tangible a payment is, the more we tend to consume. Coins and notes, which we can see, feel, and smell, is the most transparent form of payment. Credit cards or prepaid accounts are not transparent.
	Be ethical. Due to the Cashless Effect, customers will possibly end up spending more money than they actually have and in turn cause them to fall into debt. This puts more responsibility on you as a designer. Be ethical.
	Combat overspending. If you want to help customers from overspending, consider creating a budget, imposing a credit limit, or increasing friction for big expenses.

### Rationale
The more effortless a sale is, the less conscious effort it requires and the more revenue it will generate. Simplicity pays off. We are more aware of the exchange of value that occurs, when we pay with cash as it is visible and tangible and similarly lose it when we pay by credit card. The Cashless Effect disregards purchase size and influences both a $1 sale and a $1000 sale.

### Usage Examples
Less friction results in more sales. Make paying effortless. The less tangible a payment is, the more we tend to consume. Coins and notes, which we can see, feel, and smell, is the most transparent form of payment. Credit cards or prepaid accounts are not transparent.
	Be ethical. Due to the Cashless Effect, customers will possibly end up spending more money than they actually have and in turn cause them to fall into debt. This puts more responsibility on you as a designer. Be ethical.
	Combat overspending. If you want to help customers from overspending, consider creating a budget, imposing a credit limit, or increasing friction for big expenses.

---

## Categorization

**URL Validation:** https://ui-patterns.com/patterns/categorization

### Problem Summary
The user wants to make sense of content by browsing and grouping them into categories

### Solution
Let users categorize content into a hierarchal section. Allow users to select a hierichal, and possibly nested, category for their content that matches the hierichal categorization of the site itself.

### Rationale
Where tagging works to explain tiny distinctions and details in content, categories represent broader and more easily explained distinctions.
Having multiple categories help to wall section off from each other and help suggest what content is to be found, needed and appropriate for a site.
Categorization is the process in which ideas and objects are recognized, differentiated, and understood1. Categories help us make sense of the world faster and more easily. We seek to categorize all we experience in an attempt to explain how the world works  how our knowledge is represented in the real world.

### Usage Examples
Let users categorize content into a hierarchal section. Allow users to select a hierichal, and possibly nested, category for their content that matches the hierichal categorization of the site itself.

---

## Choice Closure

**URL Validation:** https://ui-patterns.com/patterns/choice-closure

### Problem Summary
We are more satisfied with decisions when we engage in physical acts of closure

### Solution
Separate the buying experience for closure. Clearly separating the billing process (or area) from the rest of the shopping experience will help consumers gain closure more easily at the time of billing. Distinguishing one part of the shopping experience from the next will increase the sense of closure as customers complete each component parts.
	Let customers seal the deal. Take away the menus once food has been ordered, have customers put purchased wine into a 6x carrier box, offer a glass of champagne to customers after purchasing a luxury handbag, or have customers pick out their own gift box. Find physical forms of closure that imply a final decision and confidence in a sealed deal
	Reduce choice overload. In situations where customers feel an overwhelming number of choices, let an assistant carefully guide the customer through the decision-making process, while using a physical closure ritual to give customers enough autonomy to create the sense of closure themselves.

### Rationale
We perceive a decision to be more final when we engage in specific physical acts metaphorically associated with the concept of closure – such as closing a menu after selecting food. Create distinguishable separate experiences for closure such as having billing separate from browsing, or having customers collect and seal their product in-store. This can in turn help both increase satisfaction.

### Usage Examples
Separate the buying experience for closure. Clearly separating the billing process (or area) from the rest of the shopping experience will help consumers gain closure more easily at the time of billing. Distinguishing one part of the shopping experience from the next will increase the sense of closure as customers complete each component parts.
	Let customers seal the deal. Take away the menus once food has been ordered, have customers put purchased wine into a 6x carrier box, offer a glass of champagne to customers after purchasing a luxury handbag, or have customers pick out their own gift box. Find physical forms of closure that imply a final decision and confidence in a sealed deal
	Reduce choice overload. In situations where customers feel an overwhelming number of choices, let an assistant carefully guide the customer through the decision-making process, while using a physical closure ritual to give customers enough autonomy to create the sense of closure themselves.

---

## Coachmarks

**URL Validation:** https://ui-patterns.com/patterns/coachmarks

### Problem Summary
The user needs help to understand a complex user interface

### Solution
Display text, arrows, and images atop a modal overlay explaining the function of the interface.
Coachmarks represent multiple help call-outs that appear on a transparent overlay. By using text and often arrows and images, they point to and explain the functionality of the user interface.

### Rationale
Coachmarks can help explain overly complicated or novel user interfaces to users, but they do not help solve the underlying problems of poorly composed interfaces. Consider other onboarding patterns before settling with coachmarks.

### Usage Examples
Display text, arrows, and images atop a modal overlay explaining the function of the interface.
Coachmarks represent multiple help call-outs that appear on a transparent overlay. By using text and often arrows and images, they point to and explain the functionality of the user interface.

---

## Cognitive Dissonance

**URL Validation:** https://ui-patterns.com/patterns/cognitive-dissonance

### Problem Summary
When we do something that is not in line with our beliefs, we change our beliefs

### Solution
As humans, we subconsciously strive for internal consistency. Experiencing the inconsistency of cognitive dissonance leads to psychological discomfort. In turn, this leads to the higher motivation to avoid information that can contradict our own beliefs and values.  So that we can stay in balance and be happy.
Most of the time, we try to reduce our cognitive dissonance in several ways:

	Add positive belief to reduce discomfort. Avoid backpain, by exercising twice a week


	Change the behavior or cognition. “I don’t eat meat anymore.”
	Reducing the importance of discomfort to justify the conflicting behavior. Exercising twice a week will make it ok  will reduce the importance of the conflict. Here the conflict whose importance is reduced being: sitting for too long can cause back pain.
	Justify the behavior or the cognition, by altering the conflicting cognition. “I can have a cheat day with meat once a week.”
	Justify the behavior or the cognition by adding new ones. “I’ll go for a run to burn out the extra calories, I will eat now”
	Ignore or deny information that conflicts with existing beliefs. “This meat is organic, so the animal must have had a good life.”

Strategies
This principle can be a powerful tool for product designers, offering various ways to enhance user engagement and experience.

	Highlight discomfort. Users might not consciously know about a discomfort or might not be able to articulate a particular problem. Help them by highlighting how they are currently in pain and how you can help them get out of it.
	Alleviate discomfort. Frame your product or service in a way that will remove or reduce the dissonance and feelings of discomfort from a particular topic. E.g. filing taxes, working out, or staying smart.
	Change beliefs. Cognitive dissonance can be used to change one or more of the attitudes, behavior, beliefs, etc., to make the relationship between the two elements a consonant one (in harmony).
	Onboarding and User Engagement. After users invest time in customizing a product or setting up a profile, theyre more likely to engage further to justify their initial investment. Prompting users to make small commitments during onboarding can lead to increased engagement as they seek consistency with their initial decisions.
	Highlighting Disconnect. Pointing out the gap between a users stated goals and their actual behaviors can motivate change. However, its essential to approach this with sensitivity to ensure the user doesnt feel attacked or overly pressured.
	Resolving Dissonance. The presence of cognitive dissonance motivates users to reduce it. Designers can help users by providing reasons that support their product choices, showcasing reviews and testimonials, and highlighting the products value.
	Engaging in Dialogue. Interpersonal communication can produce cognitive dissonance, breaking down stereotypes and building trust. This can be especially effective in community-driven platforms or products that rely on user collaboration.
	Disarming Opposing Behavior. Understanding the opposing sides expectations and then acting differently can create cognitive dissonance. Consistent behavior thats visible and cant be ignored can yield significant results, enhancing user trust and loyalty.

However, designers must be cautious. One major pitfall in applying cognitive dissonance is becoming too aggressive in highlighting discrepancies in user behavior and beliefs. Overemphasis can make users feel judged or cornered, resulting in resistance or even disengagement from the product. Its also essential to avoid creating dissonance that doesnt offer a clear path to resolution. If users feel a mismatch between their actions and beliefs but arent provided tools or options to reconcile the difference, they might experience unnecessary distress.
Excessive reliance on inducing cognitive dissonance, especially over extended periods, can inadvertently amplify the chasm between users self-perceptions and their actual behaviors. Such a persistent tug-of-war can lead to an unintended consequence: a diminished self-esteem. For a user, constantly being reminded of their shortcomings or deviations from ideal behaviors can foster feelings of inadequacy. Over time, this could result in users distancing themselves from the platform altogether. The very tool aimed to engage might become the reason for disengagement.
To maximize the benefits and minimize the pitfalls, designers should envision the user experience as a carefully calibrated rollercoaster ride. Like the highs and lows of a coaster, cognitive dissonance should be intermittently introduced, followed by periods of relief and support.
Imagine a health app that regularly reminds users about missed workout sessions. If employed too frequently, these reminders could demotivate users. However, if, after a reminder, the app offers a tailored workout plan, supportive messages, or shares success stories, it provides that necessary relief. Then, once the user has had a chance to realign their actions with their self-perception, the app can reintroduce cognitive dissonance to push them towards their next milestone.
Too much ease and they stagnate; too much challenge and they retreat. Designers must strike the right balance, ensuring users remain motivated but not overwhelmed. Its about keeping them on track, offering support, and then gently nudging them forward when theyre ready to take the next step.

### Rationale
Our actions influence subsequent beliefs and attitudes – they arent the result of them. The presence of cognitive dissonance, of being psychologically uncomfortable, motivates us to resolve the conflict in order to reduce the dissonance. Provoke cognitive dissonance and let users resolve the conflict by taking action.
The cognitive dissonance theory, counterintuitively, suggests that our actions can influence our subsequent beliefs and attitudes. As humans, we seek consistency among our attitudes, thoughts, and beliefs. Dissonance, or the state of discomfort, arises when theres a conflict between these cognitions. This discomfort motivates us to resolve the conflict, either by reducing its importance, adding consonant cognitions, or changing the dissonant cognitions.
Cognitive Dissonance is grounded in the principle that individuals have an inherent desire to ensure consistency between their beliefs, attitudes, and behaviors. When a discrepancy arises among these elements, it results in a state of tension or discomfort, pushing individuals to resolve this inconsistency to regain cognitive harmony.

### Usage Examples
As humans, we subconsciously strive for internal consistency. Experiencing the inconsistency of cognitive dissonance leads to psychological discomfort. In turn, this leads to the higher motivation to avoid information that can contradict our own beliefs and values.  So that we can stay in balance and be happy.
Most of the time, we try to reduce our cognitive dissonance in several ways:

	Add positive belief to reduce discomfort. Avoid backpain, by exercising twice a week


	Change the behavior or cognition. “I don’t eat meat anymore.”
	Reducing the importance of discomfort to justify the conflicting behavior. Exercising twice a week will make it ok  will reduce the importance of the conflict. Here the conflict whose importance is reduced being: sitting for too long can cause back pain.
	Justify the behavior or the cognition, by altering the conflicting cognition. “I can have a cheat day with meat once a week.”
	Justify the behavior or the cognition by adding new ones. “I’ll go for a run to burn out the extra calories, I will eat now”
	Ignore or deny information that conflicts with existing beliefs. “This meat is organic, so the animal must have had a good life.”

Strategies
This principle can be a powerful tool for product designers, offering various ways to enhance user engagement and experience.

	Highlight discomfort. Users might not consciously know about a discomfort or might not be able to articulate a particular problem. Help them by highlighting how they are currently in pain and how you can help them get out of it.
	Alleviate discomfort. Frame your product or service in a way that will remove or reduce the dissonance and feelings of discomfort from a particular topic. E.g. filing taxes, working out, or staying smart.
	Change beliefs. Cognitive dissonance can be used to change one or more of the attitudes, behavior, beliefs, etc., to make the relationship between the two elements a consonant one (in harmony).
	Onboarding and User Engagement. After users invest time in customizing a product or setting up a profile, theyre more likely to engage further to justify their initial investment. Prompting users to make small commitments during onboarding can lead to increased engagement as they seek consistency with their initial decisions.
	Highlighting Disconnect. Pointing out the gap between a users stated goals and their actual behaviors can motivate change. However, its essential to approach this with sensitivity to ensure the user doesnt feel attacked or overly pressured.
	Resolving Dissonance. The presence of cognitive dissonance motivates users to reduce it. Designers can help users by providing reasons that support their product choices, showcasing reviews and testimonials, and highlighting the products value.
	Engaging in Dialogue. Interpersonal communication can produce cognitive dissonance, breaking down stereotypes and building trust. This can be especially effective in community-driven platforms or products that rely on user collaboration.
	Disarming Opposing Behavior. Understanding the opposing sides expectations and then acting differently can create cognitive dissonance. Consistent behavior thats visible and cant be ignored can yield significant results, enhancing user trust and loyalty.

However, designers must be cautious. One major pitfall in applying cognitive dissonance is becoming too aggressive in highlighting discrepancies in user behavior and beliefs. Overemphasis can make users feel judged or cornered, resulting in resistance or even disengagement from the product. Its also essential to avoid creating dissonance that doesnt offer a clear path to resolution. If users feel a mismatch between their actions and beliefs but arent provided tools or options to reconcile the difference, they might experience unnecessary distress.
Excessive reliance on inducing cognitive dissonance, especially over extended periods, can inadvertently amplify the chasm between users self-perceptions and their actual behaviors. Such a persistent tug-of-war can lead to an unintended consequence: a diminished self-esteem. For a user, constantly being reminded of their shortcomings or deviations from ideal behaviors can foster feelings of inadequacy. Over time, this could result in users distancing themselves from the platform altogether. The very tool aimed to engage might become the reason for disengagement.
To maximize the benefits and minimize the pitfalls, designers should envision the user experience as a carefully calibrated rollercoaster ride. Like the highs and lows of a coaster, cognitive dissonance should be intermittently introduced, followed by periods of relief and support.
Imagine a health app that regularly reminds users about missed workout sessions. If employed too frequently, these reminders could demotivate users. However, if, after a reminder, the app offers a tailored workout plan, supportive messages, or shares success stories, it provides that necessary relief. Then, once the user has had a chance to realign their actions with their self-perception, the app can reintroduce cognitive dissonance to push them towards their next milestone.
Too much ease and they stagnate; too much challenge and they retreat. Designers must strike the right balance, ensuring users remain motivated but not overwhelmed. Its about keeping them on track, offering support, and then gently nudging them forward when theyre ready to take the next step.

---

## Curiosity

**URL Validation:** https://ui-patterns.com/patterns/curiosity

### Problem Summary
We crave more when teased with a small bit of interesting information

### Solution
Reveal enough to arouse interest. Consider when, and what, can you hold back and reveal just enough to arouse interest so you can supply a way to take the next step.
	Do something unexpected. People will stick around long enough to figure out what is going on.
	Drip-feed information. Set up multiple posts that encourage engagement, such as joining an email list for a first look at a new product.
	Allow exploration. We get pleasure from recognizing and seeking out new knowledge and information, and the subsequent joy of learning and growing.

### Rationale
Reveal just a tiny bit to arouse interest and create a knwledge gap. As humans, we are driven to seek the information missing to closes the knowledge gap. Tease users with a fragment of the whole picture and let them take action to reveal more. You can delay filling in the missing pieces for quite a long time, but be aware of the point where you start introducing too much discomfort.

### Usage Examples
Reveal enough to arouse interest. Consider when, and what, can you hold back and reveal just enough to arouse interest so you can supply a way to take the next step.
	Do something unexpected. People will stick around long enough to figure out what is going on.
	Drip-feed information. Set up multiple posts that encourage engagement, such as joining an email list for a first look at a new product.
	Allow exploration. We get pleasure from recognizing and seeking out new knowledge and information, and the subsequent joy of learning and growing.

---

## Dashboard

**URL Validation:** https://ui-patterns.com/patterns/dashboard

### Problem Summary
The user wants to digest data from mulitple sources at a glance

### Solution
Provide real-time insight into the current state of the most important metrics of a system.
Design the dashboard around a single goal and ruthlessly prioritize the data you put into it around that goal.
Types of dashboards
There are 3 common types of dashboard, each designed for its own specific purpose.

	Operational Dashboards. Displays data that facilitates the day to day operations of a business. Common objectives could be to monitor server uptime, daily sales, daily calls made, or appointments booked. Operational dashboards become the heart of your business and often require real-time or near real-time data.
	Strategic and Executive Dashboards. Displays important KPIs (Key Performance Indicators), which executive teams track on a periodic basis  daily, weekly, or monthly. The strategic dashboard focuses on providing a high-level overview of the state of the business and addresses the core changes the business work to create. Examples of common KPIs could be revenue (compared to prior period), costs (compared to prior period), sales pipeline, etc.
	Analytical Dashboards. Displays either operational or strategic data  or both. The analytical dashboard will offer drill-down functionality, allowing users to explore data in greater details.

Some types of users might need either one of these kind of dashboards, or even two. When possible, try to separate dashboards into multiple views, each with their own purpose.

### Rationale
Enable users to make instantaneous and informed decisions at a glance by letting them monitor the major functions of a system efficiently. Indicate what items require urgent attention at the top and move less critical statistics to the bottom. A good dashboard is simple, communicates well, has a minimum of distractions, tries not to confuse, and presents information visually so it is easily perceived.

### Usage Examples
Provide real-time insight into the current state of the most important metrics of a system.
Design the dashboard around a single goal and ruthlessly prioritize the data you put into it around that goal.
Types of dashboards
There are 3 common types of dashboard, each designed for its own specific purpose.

	Operational Dashboards. Displays data that facilitates the day to day operations of a business. Common objectives could be to monitor server uptime, daily sales, daily calls made, or appointments booked. Operational dashboards become the heart of your business and often require real-time or near real-time data.
	Strategic and Executive Dashboards. Displays important KPIs (Key Performance Indicators), which executive teams track on a periodic basis  daily, weekly, or monthly. The strategic dashboard focuses on providing a high-level overview of the state of the business and addresses the core changes the business work to create. Examples of common KPIs could be revenue (compared to prior period), costs (compared to prior period), sales pipeline, etc.
	Analytical Dashboards. Displays either operational or strategic data  or both. The analytical dashboard will offer drill-down functionality, allowing users to explore data in greater details.

Some types of users might need either one of these kind of dashboards, or even two. When possible, try to separate dashboards into multiple views, each with their own purpose.

---

## Decoy Effect

**URL Validation:** https://ui-patterns.com/patterns/decoy-effect

### Problem Summary
Create a new option that is easy to discard

### Solution
Target option should asymmetric dominate. In an ideal decoy situation, there are three choices available: Target (what you want people to choose), competitor, and decoy. To be effective, the decoy must be asymmetrically dominated by the target and the competitor. In other words, the target should rate better than the decoy on all parameters (better on both A and B), where the competitor is only better than the decoy on a few parameters (better on A, but worse on B).
	Make choice less overwhelming. The more options we have, the more difficulty we have making a decision (paradox of choice) and the more regret we have making the wrong choice. By manipulating what we focus on to make a decision and providing justification for our choices, the decoy effect can help us feel less anxiety from having too many options to choose from.
	Decoys act as a new reference point for loss. According to the theory of Loss Aversion, it is more unpleasant to loose $10 than it is pleasant to gain $10. Loss aversion causes us to direct more focus toward the disadvantages when making decision. What constitutes as a loss and a gain is not set in stone and is defined relative to some reference point why decoy options can partially function by manipulating where the reference point is, changing what is perceived as a loss and what is perceived as a gain.

### Rationale
We tend to have a specific change in preference between two options when a third option is also presented. When the third option is asymmetric between the original two options, customer preference will lean toward the asymmetry. If the original two options are $5 and $10, then a third $9 option will make choice lean toward the $10 option. The decoy option is superior to the first option, but similar to the second.

### Usage Examples
Target option should asymmetric dominate. In an ideal decoy situation, there are three choices available: Target (what you want people to choose), competitor, and decoy. To be effective, the decoy must be asymmetrically dominated by the target and the competitor. In other words, the target should rate better than the decoy on all parameters (better on both A and B), where the competitor is only better than the decoy on a few parameters (better on A, but worse on B).
	Make choice less overwhelming. The more options we have, the more difficulty we have making a decision (paradox of choice) and the more regret we have making the wrong choice. By manipulating what we focus on to make a decision and providing justification for our choices, the decoy effect can help us feel less anxiety from having too many options to choose from.
	Decoys act as a new reference point for loss. According to the theory of Loss Aversion, it is more unpleasant to loose $10 than it is pleasant to gain $10. Loss aversion causes us to direct more focus toward the disadvantages when making decision. What constitutes as a loss and a gain is not set in stone and is defined relative to some reference point why decoy options can partially function by manipulating where the reference point is, changing what is perceived as a loss and what is perceived as a gain.

---

## Delay Discounting

**URL Validation:** https://ui-patterns.com/patterns/delay-discounting

### Problem Summary
We tend to choose smaller immediate rewards over larger, later rewards

### Solution
Immediacy is key. Focus on the value you can deliver to your prospects right now  or relatively soon, at least. Offer smaller and more immediate rewards over greater ones that people have to wait for.
	Immediate rewards drive behavior. Why does free shipping for orders above a specific amount drive us to buy more? We value the immediate satisfaction of not paying for shipping today over the delayed satisfaction of greater savings tomorrow. Similarly, allowing customers to delay payment will push them to convert as the reward of not paying today outweighs the reward of not having to pay at some point down the line.
	Our willingness to choose decays. There is an exponential factor of decay in our willingness to choose something now. Our desire for relative immediacy diminishes substantially over time.

### Rationale
We have a preference for rewards that arrive sooner rather than later and discount the value of the later reward by increase in delay. Consider offering the convenience of now over offering a marginally cheaper alternative later – customers will have a tendency to choose a premium service that prioritises faster delivery.

### Usage Examples
Immediacy is key. Focus on the value you can deliver to your prospects right now  or relatively soon, at least. Offer smaller and more immediate rewards over greater ones that people have to wait for.
	Immediate rewards drive behavior. Why does free shipping for orders above a specific amount drive us to buy more? We value the immediate satisfaction of not paying for shipping today over the delayed satisfaction of greater savings tomorrow. Similarly, allowing customers to delay payment will push them to convert as the reward of not paying today outweighs the reward of not having to pay at some point down the line.
	Our willingness to choose decays. There is an exponential factor of decay in our willingness to choose something now. Our desire for relative immediacy diminishes substantially over time.

---

## Delighters

**URL Validation:** https://ui-patterns.com/patterns/delighters

### Problem Summary
We remember and respond favorably to new, unexpected, and playful pleasures

### Solution
Form memorable impressions. Playful microcopy, a link to a fun video, or the gift of a compliment to a user, discovery of easter eggs such as coupons, virtual gifts, or a humorous image can help form favorable and memorable impressions that make your product stand out from the crowd.
	Too much novelty is overwhelming. The highest value from novelty and surprise comes administering it in moderate levels. The rewarding effect of the novelty  is overtaken by an aversive effect as novelty increases. There is such a thing as too much new!
	Stand out from the crowd. In a crowded marketplace where users encounter similar products frequently, delight, novelty, and surprise can help overcome habituation and make your product stand-out form the crowd.

### Rationale
Novelty and surprise can transform something very normal and maybe even boring into a pleasant experience. It can overcome the habituation effect caused by people encountering many similar products every day and lead to increased product recall and recognition and word-of-mouth. Surprise is found to be positively related to satisfaction with a product.

### Usage Examples
Form memorable impressions. Playful microcopy, a link to a fun video, or the gift of a compliment to a user, discovery of easter eggs such as coupons, virtual gifts, or a humorous image can help form favorable and memorable impressions that make your product stand out from the crowd.
	Too much novelty is overwhelming. The highest value from novelty and surprise comes administering it in moderate levels. The rewarding effect of the novelty  is overtaken by an aversive effect as novelty increases. There is such a thing as too much new!
	Stand out from the crowd. In a crowded marketplace where users encounter similar products frequently, delight, novelty, and surprise can help overcome habituation and make your product stand-out form the crowd.

---

## Chat

**URL Validation:** https://ui-patterns.com/patterns/direct-messaging

### Problem Summary
The user wants to interact privately with other individuals or groups from within the system

### Solution
Allow users to interact with groups, individuals, or the system through text messages. Elements of this design patterns often includes several screens to be designed:

	Inbox. A screen the lists the most recent messages received from other users
	Outbox / Sent. A screen that lists the most recent messages sent to other users
	New message. A screen that provides a form for the user to enter his or her message in and in turn click a Send button.

### Rationale
Chat as an interface is as old as the command line. Combining chatbots with the social interactions of direct and group messaging, chat as an interface can comprehend use cases as varied as paying your gas bill, deploying code, or building intimate social relations..

### Usage Examples
Allow users to interact with groups, individuals, or the system through text messages. Elements of this design patterns often includes several screens to be designed:

	Inbox. A screen the lists the most recent messages received from other users
	Outbox / Sent. A screen that lists the most recent messages sent to other users
	New message. A screen that provides a form for the user to enter his or her message in and in turn click a Send button.

---

## Drag and drop

**URL Validation:** https://ui-patterns.com/patterns/drag-and-drop

### Problem Summary
The user needs to perform operations on one or more objects by moving them from one place to another.

### Solution
Let users pick up and rearrange content by dragging it across the screen

### Rationale
Instinctively, many users try dragging and dropping objects in user interfaces. This conceptual metaphor with clear ties to the physical world provides a level of direct manipulation few methods can match. It is seen as one of the most effective ways to rearrange items in a list, move objects from one place to the other, or even upload files.

### Usage Examples
Let users pick up and rearrange content by dragging it across the screen

---

## Expandable Input

**URL Validation:** https://ui-patterns.com/patterns/expandable-input

### Problem Summary
The user wants to experience a main interface with as much screen real estate and with a minimum of distractions

### Solution
Expand the size of input fields as they come in focus or are filled with content
Design your controls in two modes: expanded and contracted. As the user taps a contracted control, it expands to its larger size. This can help keeping secondary functions out of the way until the user is in need of them.

### Rationale
Expandable inputs can help unclutter user interfaces by staying out of sight until needed. For multiple purpose user interfaces, it can be helpful to let optional actions, such as searching, posting, or commenting, attract a minimum of attention.

### Usage Examples
Expand the size of input fields as they come in focus or are filled with content
Design your controls in two modes: expanded and contracted. As the user taps a contracted control, it expands to its larger size. This can help keeping secondary functions out of the way until the user is in need of them.

---

## Favorites

**URL Validation:** https://ui-patterns.com/patterns/favorites

### Problem Summary
The user wants to pick out items for later consumption

### Solution
Let users curate a personalized list of favorite items.
Provide a way for users to save items of particular interest for curation or later consumption. Consider allowing tagging or adding descriptions or other metadata to help users recall items later.
Provide a favorite button, juxtaposed to items in a list view or placed within a detail view. The button usually takes the shape of a star or heart. Additionally, consider providing a list of items that the user has favored.
Choosing to favorite content is an on/off choice. This pattern does not allow associating meta-data to the favorite or in other ways categorizing the content.
This pattern focuses on personal organization rather than promoting content. It allows users to either publicly or privately pick out content, anywhere in the product, that they might want to come back to later. Contrary to liking or sharing, which tends to get lost in activity streams, favorites can be used to mark content to read later or which might come in handy again.

### Rationale
Favorites can help users create sense in overwhelming sets of data and let aspiring users borrow sense from those they look up to.
Assigning favorite status is a quick way of discerning preferred content from regular content.

### Usage Examples
Let users curate a personalized list of favorite items.
Provide a way for users to save items of particular interest for curation or later consumption. Consider allowing tagging or adding descriptions or other metadata to help users recall items later.
Provide a favorite button, juxtaposed to items in a list view or placed within a detail view. The button usually takes the shape of a star or heart. Additionally, consider providing a list of items that the user has favored.
Choosing to favorite content is an on/off choice. This pattern does not allow associating meta-data to the favorite or in other ways categorizing the content.
This pattern focuses on personal organization rather than promoting content. It allows users to either publicly or privately pick out content, anywhere in the product, that they might want to come back to later. Contrary to liking or sharing, which tends to get lost in activity streams, favorites can be used to mark content to read later or which might come in handy again.

---

## Flagging  Reporting

**URL Validation:** https://ui-patterns.com/patterns/flagging-and-reporting

### Problem Summary
The user wants to mark inappropriate content for moderation

### Solution
Let users report content for moderation

### Rationale
For sites based on user-generated content and user interaction, flagging and reporting is a vital design pattern. Let users help discover content necessary for administrators to review for removal or categorization. Users are most often happy to help with the overwhelming task of surveilling and managing user-generated content produced in a community.

### Usage Examples
Let users report content for moderation

---

## Follow

**URL Validation:** https://ui-patterns.com/patterns/follow

### Problem Summary
The user wants to track and keep up to date with activity on topics or themes, not just people

### Solution
Allow users to select items that they want to stay up to date with. Let users follow topics, themes, channels, events, or people and show related updates in the users Activity Stream. Contrary to the Friend design pattern, users do not have to worry about how many of their friends are using the same service or if their friends share the same taste.
Users can select items (objects) which they want to stay up to date with. The most common object to follow is other people (friends), but other popular objects are channels, artists, and interests.
As a consequence of following, users can keep track of- and receive updates from the objects follows. Typically, updates are shown in users Activity Stream or used to suggest new, related, and undiscovered objects similar to what is already followed.

### Rationale
Users can gain access to a lot of varied content by “following” the activities and recommendations of other users and this pattern allows them to do so without having to worry about how many of their actual friends are using the application.
Content shared with followers on sites like Google+ and Pinterest makes the content curation community possible and users can choose to follow topics, events, themes or even people to get fresh content built by and around the channel being followed. For the same reason friend lists will become an increasingly important UI design pattern, so will the Follow pattern.

### Usage Examples
Allow users to select items that they want to stay up to date with. Let users follow topics, themes, channels, events, or people and show related updates in the users Activity Stream. Contrary to the Friend design pattern, users do not have to worry about how many of their friends are using the same service or if their friends share the same taste.
Users can select items (objects) which they want to stay up to date with. The most common object to follow is other people (friends), but other popular objects are channels, artists, and interests.
As a consequence of following, users can keep track of- and receive updates from the objects follows. Typically, updates are shown in users Activity Stream or used to suggest new, related, and undiscovered objects similar to what is already followed.

---

## Framing

**URL Validation:** https://ui-patterns.com/patterns/framing

### Problem Summary
The way a fact is presented greatly alters our judgement and decisions

### Solution
Create a frame. Frame evidence as either a loss (10% fat) or a gain (90% lean) to help others see things the same way as you.
	Reframe statistics through comparison. Evidence are reinterpreted when compared and contrasted with other data. Reframe facts, that in one light might seem negative to something positive, by comparing and contrasting to industry standards or similar. Your product might have a 3 out of 5 star rating, but the competition has a 2 star rating.
	Losses loom larger than gains. We are more likely to act on an offer when the marketing message is framed as a loss rather than a gain. Dont lose your offer works better than Heres an offer.

### Rationale
The same piece of information can be reframed substantially to influence decision-making through words, numbers, and imagery. The same fact can generally be framed as a loss or gain and as we try to avoid risks when a choice is framed positively and seek risk when framed negatively, decisions will also vary. An implied story makes more desirable choices seem obvious.
We determine value by comparing and contrasting things. The value of particular items can seem very different in various situations, depending on the comparison. An implied story makes more desirable choices seem obvious.
We tend to avoid risk when a positive frame is presented but seek risks when a negative frame is presented

### Usage Examples
Create a frame. Frame evidence as either a loss (10% fat) or a gain (90% lean) to help others see things the same way as you.
	Reframe statistics through comparison. Evidence are reinterpreted when compared and contrasted with other data. Reframe facts, that in one light might seem negative to something positive, by comparing and contrasting to industry standards or similar. Your product might have a 3 out of 5 star rating, but the competition has a 2 star rating.
	Losses loom larger than gains. We are more likely to act on an offer when the marketing message is framed as a loss rather than a gain. Dont lose your offer works better than Heres an offer.

---

## Frequently Asked Questions (FAQ)

**URL Validation:** https://ui-patterns.com/patterns/frequently-asked-questions-faq

### Problem Summary
The user has questions concerning a site and its related services

### Solution
Provide a space where users can get answers to common questions.
Organize Frequently Asked Questions (FAQ) into a separate and routinely maintained section on your site. Keep questions short, limited, scannable, searchable, and well organized using the language of your users. Allow users to quickly assess whether an answer applies to their particular situation and provide clear actions to get started with a solution.
Focus on information
When it comes to FAQ pages, your ultimate goal is to let users find the information they are looking for as easily and quickly as possible. Your main design goal is to present its content in the most efficient and effective way possible. Information comes first  dont let design decisions overshadow content.
Designing longer FAQs
The longer your FAQ page is, the more attention you need toward making it easy for users to find the answers they are looking for. There are several tools available:

	Organize questions in categories. The categories you choose is up to you, however, your goal should be to make it easier for users to find the information they are looking for. Make them logical and without too many questions within them. Consider finding the right categorization through card-sorting.
	Let users search questions. Allowing users to search questions will help users browse through possibly hundreds of questions fast. However, the words your users choose might not be the ones you chose yourself. Browse through the search log of your FAQ page to discover with what words your users think and what wording it makes sense for you to use yourself.
	Prioritize the most frequently asked questions first. A 80/20 rule typically applies to FAQs: 80% of queries can be answered by 20% of your documented answers.

Card sorting
A good tool to help you find a user-centered categorization is through card sorting2. Card sorting will help design and evaluate your information architecture by letting users organize topics into categories that makes sense for them as well as labelling them.
Let users ask new questions
If a user cant find the answer to their question within your FAQ, its likely they will want to ask you directly. Provide a way to let them ask a free-form text question and be sure to be able to answer them quickly.
Few people go to the FAQ front page directly
Most people search for their answer through search engines like Google. Design each answer page so that you include enough context as if it was a landing page. Align words and phrases used in the answer with what people might search for on Google. Reassure users that theyve landed on the right page that will help them get answers to their question: place keywords that will trigger users to read more as they first scan the page.

### Usage Examples
Provide a space where users can get answers to common questions.
Organize Frequently Asked Questions (FAQ) into a separate and routinely maintained section on your site. Keep questions short, limited, scannable, searchable, and well organized using the language of your users. Allow users to quickly assess whether an answer applies to their particular situation and provide clear actions to get started with a solution.
Focus on information
When it comes to FAQ pages, your ultimate goal is to let users find the information they are looking for as easily and quickly as possible. Your main design goal is to present its content in the most efficient and effective way possible. Information comes first  dont let design decisions overshadow content.
Designing longer FAQs
The longer your FAQ page is, the more attention you need toward making it easy for users to find the answers they are looking for. There are several tools available:

	Organize questions in categories. The categories you choose is up to you, however, your goal should be to make it easier for users to find the information they are looking for. Make them logical and without too many questions within them. Consider finding the right categorization through card-sorting.
	Let users search questions. Allowing users to search questions will help users browse through possibly hundreds of questions fast. However, the words your users choose might not be the ones you chose yourself. Browse through the search log of your FAQ page to discover with what words your users think and what wording it makes sense for you to use yourself.
	Prioritize the most frequently asked questions first. A 80/20 rule typically applies to FAQs: 80% of queries can be answered by 20% of your documented answers.

Card sorting
A good tool to help you find a user-centered categorization is through card sorting2. Card sorting will help design and evaluate your information architecture by letting users organize topics into categories that makes sense for them as well as labelling them.
Let users ask new questions
If a user cant find the answer to their question within your FAQ, its likely they will want to ask you directly. Provide a way to let them ask a free-form text question and be sure to be able to answer them quickly.
Few people go to the FAQ front page directly
Most people search for their answer through search engines like Google. Design each answer page so that you include enough context as if it was a landing page. Align words and phrases used in the answer with what people might search for on Google. Reassure users that theyve landed on the right page that will help them get answers to their question: place keywords that will trigger users to read more as they first scan the page.

---

## Fresh Start Effect

**URL Validation:** https://ui-patterns.com/patterns/fresh-start-effect

### Problem Summary
We are more likely to achieve goals set at the start of a new time period

### Solution
Frame time markers as opportunities. Frame certain points in time as opportunities for a fresh start. Consider whether you can frame other time scales than just the new year coming. If applicable, use efforts of previous attempts as an anchor to beat.* Consider decay. Research for how long fresh-start feelings persist. The fresh start effect in relation to labor day might decay faster than for a new year.
	Consider frequency. The simpler the behavior required to take action is, the more likely it is that users will be motivated for behavior change.

### Rationale
Time based landmarks such as a new week, month, year, national holiday, school semesater, or an anniversary, marks the passage of a mental accounting period assigning past imperfections to the previous period. In turn, this motivates to big-picture thinking and aspirational behaviors for the coming period of time and can hellp overcome willpower problems that keeps us from achieving our goals.

### Usage Examples
Frame time markers as opportunities. Frame certain points in time as opportunities for a fresh start. Consider whether you can frame other time scales than just the new year coming. If applicable, use efforts of previous attempts as an anchor to beat.* Consider decay. Research for how long fresh-start feelings persist. The fresh start effect in relation to labor day might decay faster than for a new year.
	Consider frequency. The simpler the behavior required to take action is, the more likely it is that users will be motivated for behavior change.

---

## Friend

**URL Validation:** https://ui-patterns.com/patterns/friend

### Problem Summary
The user wants to form a mutually agreed connection with another person

### Solution
Let users form mutually agreed connections with each other.
The mutual agreed two-way connection of friending is in contrast to the one-way Follow pattern, and implies a connection of a more personal type. Having an online friend relationship often gives each party access to the exchange of more actions and information between them.

### Usage Examples
Let users form mutually agreed connections with each other.
The mutual agreed two-way connection of friending is in contrast to the one-way Follow pattern, and implies a connection of a more personal type. Having an online friend relationship often gives each party access to the exchange of more actions and information between them.

---

## Friend list

**URL Validation:** https://ui-patterns.com/patterns/friend-list

### Problem Summary
The user wants to keep track of and engage a subset of their friends on the site in a meaningful way.

### Solution
Show a users connections or friends in a manageable list. This pattern is often combined with the Follow pattern.

### Rationale
Friend lists can be used to help users engage with your web application in a better way by keeping up with how other people they know are using the application.
Friend lists also come in handy when the users want to control who they share with. Whether it’s one-on-one communication or keeping track of someone’s tastes and preferences, the way users explore their blossoming friend groups will become increasingly contextual, requiring friends to become a more integral part of the content-consumption experience.

### Usage Examples
Show a users connections or friends in a manageable list. This pattern is often combined with the Follow pattern.

---

## Halo Effect

**URL Validation:** https://ui-patterns.com/patterns/halo-effect

### Problem Summary
We let impressions created in one area influence opinions in another area

### Solution
First impressions matter. The Halo effect depicts that people do judge a book by its cover. Having a good initial experience with a product tends leads to higher rating of intuitiveness, reliability, and security of the rest of your product and experience.
	Spillovers happen. Peoples perception of one aspect of an organisation, such as its customer service, can influence how people perceive the rest of its operations and the company as a whole.

### Rationale
We tend to like (or dislike) everything about a person – including things we have not observed. We strive toward maintaining a simple and coherent view of the world and suppress ambiguity. We interpret things in a way that makes them coherent with the context. The halo (positive) and horn (negative) effects increases the weight of first impressions – sometimes to the point that subsequent information is mostly wasted.
Consumers are willing to pay more money for a brand they already know and trust. Subsequent new products by a brand will benefit from the brands halo effect.

### Usage Examples
First impressions matter. The Halo effect depicts that people do judge a book by its cover. Having a good initial experience with a product tends leads to higher rating of intuitiveness, reliability, and security of the rest of your product and experience.
	Spillovers happen. Peoples perception of one aspect of an organisation, such as its customer service, can influence how people perceive the rest of its operations and the company as a whole.

---

## Hedonic Adaptation

**URL Validation:** https://ui-patterns.com/patterns/hedonic-adaptation

### Problem Summary
We return to a stable level of happiness despite major positive or negative events

### Solution
Slow it down by breaking it up. Slow down the fading process by breaking up the experience into smaller bits. Think of ways to keep users in a state of permanent and slight hunger; they will love you for it. Being asked, they will say that they want it all at the same time.
	Too much good. Our expectations and desires rise in tandem to the levels of good or bad we are experiencing. Receiving a pay rise provide immediate happiness, but the feeling quickly fades as we get accustomed to it. Consider how you can keep users in state of permanent slight craving to keep expectations low and users happy.
	Maximize the duration of happiness. What users think they want is not what will make them happy. Build anticipation and positive hype by gradually releasing products or content to users. By limiting access, each release will function as a much anticipated reward.

### Rationale
No matter how good or bad a new experience makes us feel, our feelings eventually revert back to normal, shifting adaption levels to the new baseline. Lottery winners are no happier than non-winners eighteen months later. Restricting pleasure increases the feeling of pleasure.

### Usage Examples
Slow it down by breaking it up. Slow down the fading process by breaking up the experience into smaller bits. Think of ways to keep users in a state of permanent and slight hunger; they will love you for it. Being asked, they will say that they want it all at the same time.
	Too much good. Our expectations and desires rise in tandem to the levels of good or bad we are experiencing. Receiving a pay rise provide immediate happiness, but the feeling quickly fades as we get accustomed to it. Consider how you can keep users in state of permanent slight craving to keep expectations low and users happy.
	Maximize the duration of happiness. What users think they want is not what will make them happy. Build anticipation and positive hype by gradually releasing products or content to users. By limiting access, each release will function as a much anticipated reward.

---

## IKEA effect

**URL Validation:** https://ui-patterns.com/patterns/ikea-effect

### Problem Summary
We place a disproportionately high value on products we helped create

### Solution
Increase customer satisfaction. Actively involve users in not only designing, marketing, and testing of products, but also building them, to maximize their satisfaction. Add an aspect of customer-owned creation into your existing product. The biggest challenge lies in convincing users to engage in the kinds of labor that will lead them to value products more highly.
	Find appropriate challenges. Labor leads to love only when that labor is successful. Be careful to create tasks that are not too difficult as to lead to an inability to complete the task. Start with low effort personalization options such as adding customization options and progress from there.
	Can lead to change aversion. We tend to over-commit to efforts in which we have previously invested just as we over-value products we have been part of building. This leads to our tendency to be less likely to abandon ideas or projects that we have previously put labor into.

### Rationale
Allow customers to be involved in the creation of your product to establish a powerful emotional connection between the two. We will pay more for something we have put work into than if we bought it ready-made. Customers are willing to pay a premium for products they have customized. The effect is not simply due to the amount of time spent on the creations, as dismantling a previously built product will make the effect disappear.

### Usage Examples
Increase customer satisfaction. Actively involve users in not only designing, marketing, and testing of products, but also building them, to maximize their satisfaction. Add an aspect of customer-owned creation into your existing product. The biggest challenge lies in convincing users to engage in the kinds of labor that will lead them to value products more highly.
	Find appropriate challenges. Labor leads to love only when that labor is successful. Be careful to create tasks that are not too difficult as to lead to an inability to complete the task. Start with low effort personalization options such as adding customization options and progress from there.
	Can lead to change aversion. We tend to over-commit to efforts in which we have previously invested just as we over-value products we have been part of building. This leads to our tendency to be less likely to abandon ideas or projects that we have previously put labor into.

---

## Inaction Inertia Effect

**URL Validation:** https://ui-patterns.com/patterns/inaction-inertia-effect

### Problem Summary
We are less likely to buy having previously missed a more attractive offer

### Solution
You need to consider several factors when putting your product on a discount:

	A discount needs a reason. We tend to be unwilling to grab the same product after we miss a discount as the discount reduces the perceived value of the product and anchors our expectations at a new, lower, baseline. Avoid short-term price wars as you risk setting a new inflexible expectation regarding the too good bargain. Customers need to understand why the product is discounted and why it shortly wont be.
	Change appearance from offer to offer. Change product characteristics or promotional formats to avoid product price comparison by changing how the product appears or is promoted. Think in season, size, quantity, and other things that can make the offer stand out from how its regularly represented.
	Reduce comparability. When two promotions are directly comparable (for instance through price alone), consumers perceive the opportunities more comparable, which results in consumers expressing higher inaction inertia.

### Rationale
When missing an appealing offer, a less attractive but still desirable deal is likely to be forfeited. As the difference between the first and second offer grows, so does the prominence of the effect. The effect can be explained by regret, as missing is seen as a loss, and as a devaluation of the later offer, as the first offer seems to serve as an anchor against the current one.

### Usage Examples
You need to consider several factors when putting your product on a discount:

	A discount needs a reason. We tend to be unwilling to grab the same product after we miss a discount as the discount reduces the perceived value of the product and anchors our expectations at a new, lower, baseline. Avoid short-term price wars as you risk setting a new inflexible expectation regarding the too good bargain. Customers need to understand why the product is discounted and why it shortly wont be.
	Change appearance from offer to offer. Change product characteristics or promotional formats to avoid product price comparison by changing how the product appears or is promoted. Think in season, size, quantity, and other things that can make the offer stand out from how its regularly represented.
	Reduce comparability. When two promotions are directly comparable (for instance through price alone), consumers perceive the opportunities more comparable, which results in consumers expressing higher inaction inertia.

---

## Inline Hints

**URL Validation:** https://ui-patterns.com/patterns/inline-hints

### Problem Summary
The user wants to learn about new or unfamiliar interface features in an unobtrusive way

### Solution
Blend in hints and coaching with content for a seamless experience.
Use the language of the existing layout to seamlessly blend in tips and coaching. The integrated experience of using the shapes of normal and everyday content allows for a more easily readable and relevant form of instruction that doesnt interrupt or obscure a content experience.
Hints are integrated seamlessly into the layout of surrounding content so that they do not obstruct or interrupt user interaction. Inline hints do not need to be dismissed although they are seen to be dismissible, to disappear after continued use, or, in the case of Blank Slates, when the user populates the screen1.
Do not use this pattern if you want to be absolutely sure users have seen your hint, as the subtle appearance that flows the rest of the content is at the risk of being ignored. Use Inline Hints to reinforce other instructions provided elsewhere in the interface.
As Inline Hints blend in with the rest of the content, users get easily confused if the hints information is not relevant to its surrounding content. Do not overuse them; make sure they are relevant and do not overwhelm the primary content experience.

### Rationale
By having inline hints take the shape of normal, everyday content, designers hope that they will be more easily readable and relevant than other forms of instruction.

### Usage Examples
Blend in hints and coaching with content for a seamless experience.
Use the language of the existing layout to seamlessly blend in tips and coaching. The integrated experience of using the shapes of normal and everyday content allows for a more easily readable and relevant form of instruction that doesnt interrupt or obscure a content experience.
Hints are integrated seamlessly into the layout of surrounding content so that they do not obstruct or interrupt user interaction. Inline hints do not need to be dismissed although they are seen to be dismissible, to disappear after continued use, or, in the case of Blank Slates, when the user populates the screen1.
Do not use this pattern if you want to be absolutely sure users have seen your hint, as the subtle appearance that flows the rest of the content is at the risk of being ignored. Use Inline Hints to reinforce other instructions provided elsewhere in the interface.
As Inline Hints blend in with the rest of the content, users get easily confused if the hints information is not relevant to its surrounding content. Do not overuse them; make sure they are relevant and do not overwhelm the primary content experience.

---

## Investment Loops

**URL Validation:** https://ui-patterns.com/patterns/investment-loops

### Problem Summary
Let users invest their effort in setting themselves up for a future reward

### Solution
Find ways for users to invest time, money, information, or effort into a product to set themselves up for future rewards. By sending a message to a friend, users set themselves up for receiving a reply – a future reward and trigger to get back into your product and conduct new behavior. In this way a habit loop is formed. With the anticipation of a future reward to come, the likelihood of users coming back is greater.

	Get people to invest. Let the user do work (investment) in the anticipation of future rewards (not immediate) that make the likelihood of users coming back for another pass in the loop more likely. Investments like this can help set up the trigger that is going to help bring users back int the loop. Consider what the simplest behavior is the the user can do in anticipation of a reward.
	Investments store value. For each pass in the loop, more value is stored in the product (users investments), effectively improving the product with use.
	Map out triggers. Consider what external triggers need to be in place to get the user to the product, but equally important how can you setup triggers within your product (internal triggers) that gets your users coming back.

### Rationale
Setting up cycles of recurring triggers, actions, and investments will possibly set users up for coming back for more.

### Usage Examples
Find ways for users to invest time, money, information, or effort into a product to set themselves up for future rewards. By sending a message to a friend, users set themselves up for receiving a reply – a future reward and trigger to get back into your product and conduct new behavior. In this way a habit loop is formed. With the anticipation of a future reward to come, the likelihood of users coming back is greater.

	Get people to invest. Let the user do work (investment) in the anticipation of future rewards (not immediate) that make the likelihood of users coming back for another pass in the loop more likely. Investments like this can help set up the trigger that is going to help bring users back int the loop. Consider what the simplest behavior is the the user can do in anticipation of a reward.
	Investments store value. For each pass in the loop, more value is stored in the product (users investments), effectively improving the product with use.
	Map out triggers. Consider what external triggers need to be in place to get the user to the product, but equally important how can you setup triggers within your product (internal triggers) that gets your users coming back.

---

## Invite friends

**URL Validation:** https://ui-patterns.com/patterns/invite-friends

### Problem Summary
The user wants to experience the application with their friends.

### Solution
Provide a way of letting users share an experience with similar others. Make the process of inviting other people to use the application simple and easy to complete.
We are more likely to agree to a request or invitation to perform an action from people we know and like than from strangers. Providing users with a way of connecting with and sharing the app with friends give them a better, more immersive experience even if just in terms of more content.
The Invite friends pattern is often built into an onboarding process or even as the Blank slate design.

### Rationale
If an experience is enjoyable or useful enough, users will want to share it with friends and similar others. If users arent connected to the experience already, they will need to be invited through an invitation.

### Usage Examples
Provide a way of letting users share an experience with similar others. Make the process of inviting other people to use the application simple and easy to complete.
We are more likely to agree to a request or invitation to perform an action from people we know and like than from strangers. Providing users with a way of connecting with and sharing the app with friends give them a better, more immersive experience even if just in terms of more content.
The Invite friends pattern is often built into an onboarding process or even as the Blank slate design.

---

## Isolation Effect

**URL Validation:** https://ui-patterns.com/patterns/isolation-effect

### Problem Summary
Items that stand out from their peers are more memorable

### Solution
Make important information or key actions visually distinctive.
The Isolation Effect, also known as the Von Restorff Effect, proposes that one item that differs from multiple similar objects that are present, the one item that differs will be more likely to be remembered. When the item in question stands out less, the likelihood of it being remembered similarly decreases.
Inferred, people value a thing differently depending on whether it is placed in isolation and whether it is placed next to an alternative. One choice can be made to look more attractive, when placed next to an alternative, to which it distinctively outranks in some respect.

	Guide through contrast. Meaningful and helpful contrast between items will make them stand out and ease the decision making of the user.
	Use sparingly. Over-use of the Isolation Effect will devalue its presence and may lead to confusion and reduce aesthetics and the users ability to choose.
	Reason the isolation. So you got the attention, but also make sure the the user can understand why you singled out that item. Show your rationale of why this product is more important than others you offer.

### Rationale
Being different is more memorable. Being positively remembered makes you stand out from the crowd. Create meaningful and helpful contrasts between products. Use color, shape, position, and texture to accentuate contrast. We remember more positively, if we understand a meaningful rationale behind the accentuation.
We remember things that stand out. This is the reason why CTA (Call-to-Action) buttons stand out and look different from the rest of the actions buttons on the same page.

### Usage Examples
Make important information or key actions visually distinctive.
The Isolation Effect, also known as the Von Restorff Effect, proposes that one item that differs from multiple similar objects that are present, the one item that differs will be more likely to be remembered. When the item in question stands out less, the likelihood of it being remembered similarly decreases.
Inferred, people value a thing differently depending on whether it is placed in isolation and whether it is placed next to an alternative. One choice can be made to look more attractive, when placed next to an alternative, to which it distinctively outranks in some respect.

	Guide through contrast. Meaningful and helpful contrast between items will make them stand out and ease the decision making of the user.
	Use sparingly. Over-use of the Isolation Effect will devalue its presence and may lead to confusion and reduce aesthetics and the users ability to choose.
	Reason the isolation. So you got the attention, but also make sure the the user can understand why you singled out that item. Show your rationale of why this product is more important than others you offer.

---

## Keyboard Shortcuts

**URL Validation:** https://ui-patterns.com/patterns/keyboard-shortcuts

### Problem Summary
The user wants to perform repetitive tasks faster

### Solution
Allow users to trigger actions faster with keyboard commands.
Typically keyboard shortcuts are made for commands that are part of frequent or repetitive user tasks.
When adding shortcuts to your application, keep away from using existing system shortcuts or shortcuts that already used elsewhere in another context in the same application. Avoid repurposing shortcuts that users have already adapted into their workflow1.
You might want to consider adding keyboard shortcut information to menu items and button and icon tooltips, if available.

### Rationale
Ease access to repetitive tasks by providing skilled users with keyboard shortcuts to their associated actions. Reduce the total time spent, the steps needed, and mental energy wasted to complete a task without making it harder on novice users.
Keyboard shortcuts accelerate exposition of program function to users through keypresses rather than mouse clicks. This can greatly help speed up task completion time as the user does not need to switch modes from using they keyboard to the mouse; hands can stay on the keyboard1.

### Usage Examples
Allow users to trigger actions faster with keyboard commands.
Typically keyboard shortcuts are made for commands that are part of frequent or repetitive user tasks.
When adding shortcuts to your application, keep away from using existing system shortcuts or shortcuts that already used elsewhere in another context in the same application. Avoid repurposing shortcuts that users have already adapted into their workflow1.
You might want to consider adding keyboard shortcut information to menu items and button and icon tooltips, if available.

---

## Leaderboard

**URL Validation:** https://ui-patterns.com/patterns/leaderboard

### Problem Summary
Users want to know who are the very best performers in a category or overall

### Solution
List a fixed number of competitors ranked by score from highest to lowest.
Allow ranked users in a highly competitive community to know who are the very best performers in a category or overall. Leaderboards can grow too stable and elite and thereby discourage rookie users from participating. Use with caution and only if the primary purpose of the community is competition, as introducing leaderboards can easily lead to gaming and non-constructive community behaviors.
Multiple views
Consider providing multiple views of a leaderboard across time (all-time, weekly, daily) and category (most points, most shares, etc.). All-time views are usually stable and sometimes (too) stagnant, why you should consider making the default view weekly or daily to showcase the latest movers1.
More design tips

	Show where the user is placed. Show the users standing and who are immediately above and below them. This will allow users to always have the possibility of climbing without seeing users they will never catch up with.
	Leaderboards should be contextual. Users should be compared to similar users, who are active and involved at the same level or time.
	Leaderboards among friends. Consider showing users leaderboards containing their friends or other local users. The impulse to compete against people you know is much stronger than to compete against strangers online.
	Leaderboards should be updated continuously. Stale data or rankings that change slowly can discourage users so make to always give users a sense of progress and gratification.

### Usage Examples
List a fixed number of competitors ranked by score from highest to lowest.
Allow ranked users in a highly competitive community to know who are the very best performers in a category or overall. Leaderboards can grow too stable and elite and thereby discourage rookie users from participating. Use with caution and only if the primary purpose of the community is competition, as introducing leaderboards can easily lead to gaming and non-constructive community behaviors.
Multiple views
Consider providing multiple views of a leaderboard across time (all-time, weekly, daily) and category (most points, most shares, etc.). All-time views are usually stable and sometimes (too) stagnant, why you should consider making the default view weekly or daily to showcase the latest movers1.
More design tips

	Show where the user is placed. Show the users standing and who are immediately above and below them. This will allow users to always have the possibility of climbing without seeing users they will never catch up with.
	Leaderboards should be contextual. Users should be compared to similar users, who are active and involved at the same level or time.
	Leaderboards among friends. Consider showing users leaderboards containing their friends or other local users. The impulse to compete against people you know is much stronger than to compete against strangers online.
	Leaderboards should be updated continuously. Stale data or rankings that change slowly can discourage users so make to always give users a sense of progress and gratification.

---

## Modal

**URL Validation:** https://ui-patterns.com/patterns/modal-windows

### Problem Summary
The user needs to take an action or cancel the overlay until he can continue interacting with the original page

### Solution
Introduce a mode in which users cannot interact with your application until the mode is closed. Interrupt the user’s attention and halt all other actions until a message is dealt with or dismissed.
Matching titles
Matching button text with the title of the modal increases the feeling of familiarity. As modals introduce a new inturrupting mode, chances are that users wont connect the action they just performed with the modal popping up. Make sure they know where the modal is coming from.
Allow escape
Allow users to escape the mode by letting them close the modal window when they need to. Popular conventions for close buttons is an X icon in the top right corner and/or a Close or Cancel button at the bottom of the modal window. The ESC key is also often a conventional keyboard shortcut to closing modals  so is clicking outside the modal window.

### Rationale
Although effective in focusing attention, introducing multiple modes comes with the risk of introducing mode errors where the user forgets the state of the interface and tries to perform actions appropriate to a different mode.

### Usage Examples
Introduce a mode in which users cannot interact with your application until the mode is closed. Interrupt the user’s attention and halt all other actions until a message is dealt with or dismissed.
Matching titles
Matching button text with the title of the modal increases the feeling of familiarity. As modals introduce a new inturrupting mode, chances are that users wont connect the action they just performed with the modal popping up. Make sure they know where the modal is coming from.
Allow escape
Allow users to escape the mode by letting them close the modal window when they need to. Popular conventions for close buttons is an X icon in the top right corner and/or a Close or Cancel button at the bottom of the modal window. The ESC key is also often a conventional keyboard shortcut to closing modals  so is clicking outside the modal window.

---

## Morphing Controls

**URL Validation:** https://ui-patterns.com/patterns/morphing-controls

### Problem Summary
The user wants to only be presented with controls available to the current mode

### Solution
Information presented and actions available in a user interface element depend on its mode. When a video is paused, the play command is available, but pause is not.
Design affordance in each mode toward the most common or wanted interactions and emphasize asymmetry, incompleteness, or something being wrong to push users toward changing modes.
Be sure to keep a consistent look between each state of the control that morphs. Font and text size should stay the same, but colors may differ.
Morphing Controls work well with binary actions, such as:

	On/Off
	Like/Unlike
	Follow/Unfollow

### Usage Examples
Information presented and actions available in a user interface element depend on its mode. When a video is paused, the play command is available, but pause is not.
Design affordance in each mode toward the most common or wanted interactions and emphasize asymmetry, incompleteness, or something being wrong to push users toward changing modes.
Be sure to keep a consistent look between each state of the control that morphs. Font and text size should stay the same, but colors may differ.
Morphing Controls work well with binary actions, such as:

	On/Off
	Like/Unlike
	Follow/Unfollow

---

## Noble Edge Effect

**URL Validation:** https://ui-patterns.com/patterns/noble-edge-effect

### Problem Summary
Products of socially responsible companies are seen as superior

### Solution
Genuine goodwill leads to superior products. Authentic social goodwill of a company can change consumers perception of the quality and performance of its products.
	Align with your target audience. The Noble Edge Effect is stronger for consumers sharing similar moral values why aligning with the societal aspirations of your target audience is crucial.
	Strong effect in unchartered or ambiguous marketplaces. Social responsible behavior is more likely to influence those who are less familiar with the specific market or line of products.  In markets where people dont much about a product or where the offering is ambiguous (banking, insurance, etc.), the Noble Edge Effect can be a key differentiator.

### Rationale
As companies show genuine care and social goodwill, it spills over to improved consumer perception of the companys products. When consumers are unfamiliar in a market, companies with a noble edge attract even more consumer choice. Products are perceived as better and of higher quality only when the social goodwill of their companies are motivated by genuine kindness over self-interest

### Usage Examples
Genuine goodwill leads to superior products. Authentic social goodwill of a company can change consumers perception of the quality and performance of its products.
	Align with your target audience. The Noble Edge Effect is stronger for consumers sharing similar moral values why aligning with the societal aspirations of your target audience is crucial.
	Strong effect in unchartered or ambiguous marketplaces. Social responsible behavior is more likely to influence those who are less familiar with the specific market or line of products.  In markets where people dont much about a product or where the offering is ambiguous (banking, insurance, etc.), the Noble Edge Effect can be a key differentiator.

---

## Nostalgia Effect

**URL Validation:** https://ui-patterns.com/patterns/nostalgia-effect

### Problem Summary
Reminiscing about the past make us downplay costs

### Solution
Encourage pro-social behavior. Use nostalgia to promote pro-social behavior such as donating to a charity, participation in charitable event, or hiring volunteers. Research what nostalgia means for your audience.
	Foster social connectedness. If the goal of your product is to build and maintain long-term relationships, theming your product around nostalgia can help as it can foster social connectedness. Add a Timehop of #throwback concept to capitalize on the opportunity of reusing archived experiences.
	Anticipated nostalgia. We anticipate having nostalgic feelings for our present and future experiences. Savouring of a past experience tends to lead to stronger anticipated nostalgia of the future as people predict heightened self-esteem, social connectedness, and meaning in life.

### Rationale
When we reminisce about the past, we start favoring social connections over economic costs. Use nostalgia to promote pro-social behavior such as donating to charities, hiring volunteers for a cause, in other ways taking a social responsibility, or just getting back in touch with old friends. Nostalgia can help build long-term social relationships and foster social connectedness.

### Usage Examples
Encourage pro-social behavior. Use nostalgia to promote pro-social behavior such as donating to a charity, participation in charitable event, or hiring volunteers. Research what nostalgia means for your audience.
	Foster social connectedness. If the goal of your product is to build and maintain long-term relationships, theming your product around nostalgia can help as it can foster social connectedness. Add a Timehop of #throwback concept to capitalize on the opportunity of reusing archived experiences.
	Anticipated nostalgia. We anticipate having nostalgic feelings for our present and future experiences. Savouring of a past experience tends to lead to stronger anticipated nostalgia of the future as people predict heightened self-esteem, social connectedness, and meaning in life.

---

## Notifications

**URL Validation:** https://ui-patterns.com/patterns/notifications

### Problem Summary
The user wants to be informed about important updates and messages

### Solution
Inform your users about relevant and timely events.
Notify users about important updates while they are focused elsewhere. Adjust the rate and relevancy of notifications aptly, as they can be interruptive. Empower users to disable or change notifications in their settings. Create personalized, summarized, and timely notifications that may serve as entry points to more detailed information.
Use notifications to draw attention to important updates: messages from friends, new friend requests, relevant nearby offers, and many more.
Across devices
Once a users has consumed a notification, he or she should not see it again. Similarly, users should be able to retrieve already consumed notifications on another device more suitable for consuming the content the user was notified about. Notifications should be synced to all of a user’s devices.
Minimize interruption
Notifications are obtrusive and interruptive in its nature. It is used to direct the users attention to important events while being focused elsewhere. Make careful considerations as to when to interrupt users. Do not notify users about information already on screen (e.g. active chat conversations), technical operations not requiring user involvement, and error states that can be resolved without user action.
Allow escape
Make notifications dismissible and let users disable or change the rate of notifications in your products settings.
Provide summaries
Combine multiple notifications of the same type into a single summary notification showing how many notifications of a particular kind are pending. Consider expanding the notification, providing detailed information of the summarized notifications, once clicked.
Provide actions
Bundle action buttons with notifications, for users to quickly handle the most common tasks for a particular notification, without opening the originating screen. Let actions be clear and unambiguous and only provide them if they do not duplicate the default action. Actions should be meaningful and time-sensitive, suit the content, and allow the user to accomplish a task.

### Usage Examples
Inform your users about relevant and timely events.
Notify users about important updates while they are focused elsewhere. Adjust the rate and relevancy of notifications aptly, as they can be interruptive. Empower users to disable or change notifications in their settings. Create personalized, summarized, and timely notifications that may serve as entry points to more detailed information.
Use notifications to draw attention to important updates: messages from friends, new friend requests, relevant nearby offers, and many more.
Across devices
Once a users has consumed a notification, he or she should not see it again. Similarly, users should be able to retrieve already consumed notifications on another device more suitable for consuming the content the user was notified about. Notifications should be synced to all of a user’s devices.
Minimize interruption
Notifications are obtrusive and interruptive in its nature. It is used to direct the users attention to important events while being focused elsewhere. Make careful considerations as to when to interrupt users. Do not notify users about information already on screen (e.g. active chat conversations), technical operations not requiring user involvement, and error states that can be resolved without user action.
Allow escape
Make notifications dismissible and let users disable or change the rate of notifications in your products settings.
Provide summaries
Combine multiple notifications of the same type into a single summary notification showing how many notifications of a particular kind are pending. Consider expanding the notification, providing detailed information of the summarized notifications, once clicked.
Provide actions
Bundle action buttons with notifications, for users to quickly handle the most common tasks for a particular notification, without opening the originating screen. Let actions be clear and unambiguous and only provide them if they do not duplicate the default action. Actions should be meaningful and time-sensitive, suit the content, and allow the user to accomplish a task.

---

## Optimism Bias

**URL Validation:** https://ui-patterns.com/patterns/optimism-bias

### Problem Summary
We consistently overstate expected success and downplay expected failure

### Solution
Limit effect using other biases. Use other biases to guide decision making. For instance, use Loss Aversion to highlight potential negative effects of critical actions clear to the user and offer a straightforward and safer alternative.
	Use anchoring to force strategic thinking. To mitigate the Optimism Bias, its worthwhile to anchor in a pessimistic future first in order to keep the optimistic scenario more realistic. Simulate pre-mortems or the future, backwards exercises.
	Think strategically in both directions. Provide a more full perspective of future scenarios – positive ones and the negative ones as well.

### Rationale
As we compare ourselves to our peers, we tend to overestimate our future success and downplay our future failure. We tend to believe in the best case scenario and ignore conflicting data as we look at what has worked in the past to predict the future, but often neglect to examine if something has been overlooked. Disclaimer: the Optimism Bias doesn’t seem to kick in for people suffering with depression.

### Usage Examples
Limit effect using other biases. Use other biases to guide decision making. For instance, use Loss Aversion to highlight potential negative effects of critical actions clear to the user and offer a straightforward and safer alternative.
	Use anchoring to force strategic thinking. To mitigate the Optimism Bias, its worthwhile to anchor in a pessimistic future first in order to keep the optimistic scenario more realistic. Simulate pre-mortems or the future, backwards exercises.
	Think strategically in both directions. Provide a more full perspective of future scenarios – positive ones and the negative ones as well.

---

## Pay To Promote

**URL Validation:** https://ui-patterns.com/patterns/pay-to-promote

### Problem Summary
The user wants to pay to prioritize own content above the regular content feed in order to gain increased reach and traction.

### Solution
Let users pay to promote their content
On social platforms like Quora, Twitter, OKCupid, and LinkedIn, users can post content. Allow users to boost visibility of their own content by paying money. This form of advertising allows users to gain traction while maintaining a look and feel native to the platform.
Sites like Quora and Facebook allow users to boost their posts by paying money, which in return gives them greater visibility in the content feed above the regular non-paid content.
Dating-sites like OKCupid allow users to boost their profile in views. LinkedIn does the same albeit as part of a paid membership plan rather than by individual content like on Facebook.

### Usage Examples
Let users pay to promote their content
On social platforms like Quora, Twitter, OKCupid, and LinkedIn, users can post content. Allow users to boost visibility of their own content by paying money. This form of advertising allows users to gain traction while maintaining a look and feel native to the platform.
Sites like Quora and Facebook allow users to boost their posts by paying money, which in return gives them greater visibility in the content feed above the regular non-paid content.
Dating-sites like OKCupid allow users to boost their profile in views. LinkedIn does the same albeit as part of a paid membership plan rather than by individual content like on Facebook.

---

## Periodic Events

**URL Validation:** https://ui-patterns.com/patterns/periodic-events

### Problem Summary
Construct recurring events to build up anticipation, a sense of belonging, comfort, and a sustained interest

### Solution
Consider ways to create shared recurring experiences users can look forward to or reminisce about. Examples are weekly tips, Black Friday sales, and monthly report cards.

	Create a tradition. Recurring traditions and ceremonies creates an experience users can look forward to or reminisce about and can help foster a sense of belonging and comfort. Examples are weekly tips, monthly report cards, throwback Thursdays, and even Black Friday sales.
	Make the experience shared. Consider how all users or groups within a system can enjoy shared recurring experiences to build a sense of belonging. How can you facilitate the users share the experience with each other?
	Build a narrative. Tying a narrative structure around periodic events will provide meaning and and motivating anticipation of future events and help direct users toward appropriate action when the periodic event happens.

### Rationale
Anticipation of an upcoming event can in itself be motivating and can provide a limited period of time, where users prepare themselves potential action or commitments. Events temporarily create special places that are different from everyday places, which provides a great occation for taking action, breaking patterns, starting new habits, or changing behaviors or attitudes.

### Usage Examples
Consider ways to create shared recurring experiences users can look forward to or reminisce about. Examples are weekly tips, Black Friday sales, and monthly report cards.

	Create a tradition. Recurring traditions and ceremonies creates an experience users can look forward to or reminisce about and can help foster a sense of belonging and comfort. Examples are weekly tips, monthly report cards, throwback Thursdays, and even Black Friday sales.
	Make the experience shared. Consider how all users or groups within a system can enjoy shared recurring experiences to build a sense of belonging. How can you facilitate the users share the experience with each other?
	Build a narrative. Tying a narrative structure around periodic events will provide meaning and and motivating anticipation of future events and help direct users toward appropriate action when the periodic event happens.

---

## Picture Superiority Effect

**URL Validation:** https://ui-patterns.com/patterns/picture-superiority-effect

### Problem Summary
We remember images much better than words

### Solution
Use images to reinforce your message. Combining words with relevant images when conveying a message will significantly boost the percentage of people remembering the information they read.
	Use Conceptual Metaphors. Use visual metaphors to effortlessly explain complex concepts or form advantageous associations with your product or service.
	Not all images are created equal. Memorability of images depend on the user context, but in general we tend to remember human faces and images featuring both and object and a scene rather than just an image of an outdoor landscape. Images should focus on specific objects, but not so focused that the scene or setting disappears.

### Rationale
Pictures are recognized and recalled more quickly and easily than both written and oral language. The best results for learning comes from combining both words and images, as words allow us to explain complex or abstract concepts and images to encode those concepts for more efficient retention and recall. Images help grab attention, enhance comprehension, and help users remember your message.

### Usage Examples
Use images to reinforce your message. Combining words with relevant images when conveying a message will significantly boost the percentage of people remembering the information they read.
	Use Conceptual Metaphors. Use visual metaphors to effortlessly explain complex concepts or form advantageous associations with your product or service.
	Not all images are created equal. Memorability of images depend on the user context, but in general we tend to remember human faces and images featuring both and object and a scene rather than just an image of an outdoor landscape. Images should focus on specific objects, but not so focused that the scene or setting disappears.

---

## Playthrough

**URL Validation:** https://ui-patterns.com/patterns/playthrough

### Problem Summary
The user wants to know how to use the different features of the application.

### Solution
A dedicated and authentic space where beginners can safely explore and learn core skills.
Spare users from facing horrible failure by introducing them to core interactions. Let users learn and explore core skills before they enter the full product experience. Provide modeless text assistance and basic goals so they can play the interface but also learn the interface as they play.
A Playthrough is something that you provide, before letting someone enter a full product experience, that introduces them to the core interactions and let’s them learn and explore those core skills. This pattern is known from games, where new players are encouraged to try out a starter level, where they get modeless text assistance and some basic goals, so that they can play the game, but also learn the game, as they play.
Let users learn through real tasks
By asking users to make their first move on the application, an application can get users engaged right off the bat. This is common in applications that depend on curation by the user to get the app working.
Continue the experience seamlessly into the full product
Carry any achievements earned in the Playthrough forward into the full, and normal, product experience. Make the transition from the Playthrough to the normal product experience as seamless as possible.
Provide a skip option
Some people just want to get into deep waters form the start. Always allow escaping a Playthrough by skipping it.
Dont drag it out
Limit the playthrough to relevant core tasks and user test your way into finding out what length is comfortable for users. Some users might like longer playthroughs than others, so be sure to allow escaping the experience, but still letting users keep their achieved artifacts.

### Rationale
By allowing users to get out into the full product world early and safely, you can keep users from facing horrible failure if they hadn’t had an introduction.

### Usage Examples
A dedicated and authentic space where beginners can safely explore and learn core skills.
Spare users from facing horrible failure by introducing them to core interactions. Let users learn and explore core skills before they enter the full product experience. Provide modeless text assistance and basic goals so they can play the interface but also learn the interface as they play.
A Playthrough is something that you provide, before letting someone enter a full product experience, that introduces them to the core interactions and let’s them learn and explore those core skills. This pattern is known from games, where new players are encouraged to try out a starter level, where they get modeless text assistance and some basic goals, so that they can play the game, but also learn the game, as they play.
Let users learn through real tasks
By asking users to make their first move on the application, an application can get users engaged right off the bat. This is common in applications that depend on curation by the user to get the app working.
Continue the experience seamlessly into the full product
Carry any achievements earned in the Playthrough forward into the full, and normal, product experience. Make the transition from the Playthrough to the normal product experience as seamless as possible.
Provide a skip option
Some people just want to get into deep waters form the start. Always allow escaping a Playthrough by skipping it.
Dont drag it out
Limit the playthrough to relevant core tasks and user test your way into finding out what length is comfortable for users. Some users might like longer playthroughs than others, so be sure to allow escaping the experience, but still letting users keep their achieved artifacts.

---

## Present Bias

**URL Validation:** https://ui-patterns.com/patterns/present-bias

### Problem Summary
What we want now is not what we aspire to in the future

### Solution
Facilitate future lock-in. Help users make healthier long-term choices and secure the best long-term consequences of their decisions by segregating making a decision from receiving the consequences. Encourage customers to order groceries several days in advance to separate their present self from their future self and in turn reduce impulse purchases.
	Optimize sales for the near-future. It is more likely that customers will spend more money in the near future than in the more distant future.
	Boost impulse sales. Using the Present Bias to boost sales, you could adapt product recommendations to include impulse purchases through time-restricted special offers.

### Rationale
Our short-term desires (wants) and longer intentions (should) differ wildly. We tend to focus on and over-value immediate rewards at the expense of long-term wishes and benefits. Allow customers to perform future lock-in to help them make healthier should choices rather than caving in to here-and-now wants.

### Usage Examples
Facilitate future lock-in. Help users make healthier long-term choices and secure the best long-term consequences of their decisions by segregating making a decision from receiving the consequences. Encourage customers to order groceries several days in advance to separate their present self from their future self and in turn reduce impulse purchases.
	Optimize sales for the near-future. It is more likely that customers will spend more money in the near future than in the more distant future.
	Boost impulse sales. Using the Present Bias to boost sales, you could adapt product recommendations to include impulse purchases through time-restricted special offers.

---

## Priming Effect

**URL Validation:** https://ui-patterns.com/patterns/priming-effect

### Problem Summary
Decisions are unconsciously shaped by what we have recently experienced

### Solution
Use metaphors. Conceptual metaphors refer to information that can unconsciously help bring specific decision outcomes to mind.
	Trigger relevant emotions. Use imagery or video to create associative priming with the subsequent expected experience.
	Use visual imagery. Colors, pictures and videos all have the power to unconsciously bring up cues that might be replicated at a later point in the user experience.

### Rationale
Exposure to a word, sign, picture, or meaning anchors the idea and allows us to more quickly recognise related options. After being primed in one direction, our instinctive preference thereafter will be in a related direction. Being semantically primed eases mental processing of that information at a later stage, creating a sense of cognitive fluency and ease of use.

### Usage Examples
Use metaphors. Conceptual metaphors refer to information that can unconsciously help bring specific decision outcomes to mind.
	Trigger relevant emotions. Use imagery or video to create associative priming with the subsequent expected experience.
	Use visual imagery. Colors, pictures and videos all have the power to unconsciously bring up cues that might be replicated at a later point in the user experience.

---

## Pull to refresh

**URL Validation:** https://ui-patterns.com/patterns/pull-to-refresh

### Problem Summary
The user wants to to retrieve more data or refresh already available contents on the screen.

### Solution
As the user pulls down on the screen with a finger, visual feedback (refresh indicator) appears at the top of the list showing a progress of content update. If the user releases before reaching the refresh threshold, the refresh aborts and visual feedback disappears.
Immediate visual feedback after the action
A user’s wait time begins the moment he initiates an action (swipe the screen for content update). Immediately after that, the application should provide a visual feedback in order to communicate that it has received the request. The user’s confidence in the fact that the refresh is happening, is directly correlated to the visual feedback. You will want to let your refresh indicator continue spinning until data is loading in order to engage the user and prevent confusion.
Refresh indicator should only be triggered by user action
Refreshing content should only be triggered manually by user why the refresh indicator should appear only in conjunction with a refresh gesture. If you do want to notify users about automatically updating content (syncing), you should refrain from using the same indicator.
Meaningful state transitions
Refresh indicators act as intermediaries between different states of the view, helping users to understand what is going on as the screen changes. Refresh indicators should remain visible until the refresh activity completes and any new content is visible, or the user navigates away from the screen.

### Rationale
Why should we use pull to refresh?
Pull to refresh are sometimes considered as an extra unnecessary step to refresh, as the user has to manually trigger refreshing or the loading content process of the application. As the pull-to-refresh gesture signifies a manual request for updates, it requires a user involvement into the process and creates a superficial layer between users and their content.
In most cases such kind of operations can be performed automatically using auto-sync procedure, without user involvement. For example, when users use Gmail in the browser on their desktops the service show them the latest emails automatically (and keeps the inbox up-to-date in the background). So why would email clients on mobile devices act differently?
Manual refreshing do provide benefits for the user interface, and can act as a great supplement to syncing:

	It is convenient for users because they’re able to update the screen whenever they choose.
	It feels natural for power users. The pull-to-refresh pattern has become a standard in mobile applications. The pull-to-refresh gesture is so universal now, that its hard for developers to ignore using it as power users expect it to be part of the application experience.
	It brings context and continuity. When users open Twitter, the application won’t throwing users to an unfamiliar spot in their Twitter timeline. Instead, the app brings them to the last read tweet. If users want to load new tweets they do it manually by pull-to-refresh.
	It also saves bandwidth for data-conscious customers.

### Usage Examples
As the user pulls down on the screen with a finger, visual feedback (refresh indicator) appears at the top of the list showing a progress of content update. If the user releases before reaching the refresh threshold, the refresh aborts and visual feedback disappears.
Immediate visual feedback after the action
A user’s wait time begins the moment he initiates an action (swipe the screen for content update). Immediately after that, the application should provide a visual feedback in order to communicate that it has received the request. The user’s confidence in the fact that the refresh is happening, is directly correlated to the visual feedback. You will want to let your refresh indicator continue spinning until data is loading in order to engage the user and prevent confusion.
Refresh indicator should only be triggered by user action
Refreshing content should only be triggered manually by user why the refresh indicator should appear only in conjunction with a refresh gesture. If you do want to notify users about automatically updating content (syncing), you should refrain from using the same indicator.
Meaningful state transitions
Refresh indicators act as intermediaries between different states of the view, helping users to understand what is going on as the screen changes. Refresh indicators should remain visible until the refresh activity completes and any new content is visible, or the user navigates away from the screen.

---

## Reaction

**URL Validation:** https://ui-patterns.com/patterns/reaction

### Problem Summary
The user wants to express their emotions in a simple way

### Solution
Let users express their immediate emotions in a simple way.
Simplify rating controls by making them binary choices of emotional consent rather than fine-grained ratings of stars or scores. Use reaction activity to discover what content might be more relevant for your users.

### Rationale
Eliminating the fine-grain of stars and rating scores, this makes rating things easier for users as well as interpreting them.

### Usage Examples
Let users express their immediate emotions in a simple way.
Simplify rating controls by making them binary choices of emotional consent rather than fine-grained ratings of stars or scores. Use reaction activity to discover what content might be more relevant for your users.

---

## Reputation

**URL Validation:** https://ui-patterns.com/patterns/reputation

### Problem Summary
We adjust our personal behavior to reflect positively on how peers or the public perceive us

### Solution
Reputation is what your audience knows about your knowledge of the subject.
Reputation depends on:

	Achievements or acknowledgments from others in the area, such as, awards and testimonials.
	Your experience and the amount of years you have worked in this area.
	How involved you were with this topic  are you a key character?
	Your expertise should be verified. Have you earned certifications or have other ways of showing off your proven expertise?
	Your contribution to the area, perhaps through blogs, books, papers and products.
	Your authority

Authority and reputation are usually predetermined before your users meet you, why it can be difficult to change the audiences mind about it directly in the situation. However, its easier to change peoples perception about how trustworthy and how alike you are in the situation.

	Let people build reputation. Let users share information, contribute content, connect to other people, keep a record of their personal activities, and perform other activities that are in line with the purpose of your community.
	Encourage wanted behavior. Highlight how specific behavior on your platform can boost reputation growth, access, and capabilities. Similarly, discourage unwanted behavior by either not allowing it or making it harder to perform.
	Promote track record. Provide easy access to testimonials, reviews, accomplishments, papers, and anything that can build on the values of honesty, ethicality, and compassion.

Using Aristotles triad of appeals to communicate Reputation
Reputation is a multifaceted construct, and its influence on persuasion is undeniable. While designers often tap into reputation as a singular entity, breaking it down through the lens of Aristotles triad of appeals – ethos, pathos, and logos – can provide a more nuanced approach to showcasing it.

	Ethos is the foundation of reputation. When designers appeal to ethos, theyre emphasizing the credibility and moral character of an entity. For instance, when a financial platform showcases its certifications and regulatory compliances, its appealing to ethos. Theyre not just showcasing their expertise but emphasizing their commitment to ethical practices and moral values.
	Pathos, on the other hand, brings out the emotional dimension of reputation. A brand or individual might have a stellar reputation, but how does that resonate on an emotional level with the audience? By weaving in a storytelling that evokes emotions, designers can make their reputation efforts more relatable. Consider the story of a brand that started from humble beginnings or an individual user on a platform who overcame significant challenges. These stories dont just highlight achievements; they appeal to the audiences emotions, making the reputation feel more human and rea
	Logos provides the logical backbone to reputation. In showcasing reputation, its crucial to have evidence that supports claims. An e-commerce site, for example, might have a seller with a fantastic reputation. Still, its the detailed product descriptions, transparent customer reviews, and clear return policies that provide the logical evidence supporting this reputation. Its about ensuring that every claim made, every piece of the reputation puzzle, can be backed by clear, logical evidence.

Its multi-dimensional and can be showcased in varied ways by appealing to ethos, pathos, and logos.
Getting a design that showcases reputation right
Reputation, in essence, is a reflection of what your audience knows or believes about your knowledge of a particular subject. Its built on the pillars of achievements, experience, involvement, verified expertise, and significant contributions to a domain.
For instance, the manner in which awards, testimonials, years of experience, and the depth of involvement with a topic can shape the perception of reputation is evident in platforms like LinkedIn, where endorsements and recommendations play a pivotal role. On Stack Overflow, users earn reputation points by providing valuable answers, signaling their expertise and trustworthiness in specific areas.
However, the journey to building and maintaining a robust reputation isnt just about showcasing past accomplishments. Its also about the present actions and the avenues a platform offers for users to shape their reputation. Encouraging users to actively participate, share information, contribute content, and connect with others can be a transformative strategy. Such engagement not only amplifies the sense of community but also lets users carve out their niche, as seen on platforms like Etsy where sellers build their reputation through transparent transaction histories.
While reputation can often precede a users direct interaction with a platform, once theyre engaged, its pivotal to highlight how specific behaviors can enhance their reputation. For instance, platforms like LinkedIn and Etsy have embedded the reputation system within their core, allowing users to understand that responsible and commendable behavior will be rewarded.
Yet, in this endeavor, designers must tread carefully. Its crucial to promote a track record that champions values like honesty, ethicality, and compassion. Easy access to testimonials, reviews, and accomplishments can solidify a users trust. Conversely, designers should be wary of and actively discourage any behavior that might tarnish this trust.
While authority and reputation might be predetermined before users encounter a platform, the design has the power to either reinforce or reshape these notions. By creating avenues for users to build and showcase their reputation, and by emphasizing values that resonate with the audience, designers can craft experiences that are not just engaging but also deeply trustworthy.
Reputation can be a powerful tool. However, there are pitfalls to avoid. One major error is the temptation to artificially inflate reputation, either by purchasing fake reviews or suppressing negative ones. This manipulation can quickly backfire, damaging trust when users discern the inauthenticity. Another common oversight is not providing a platform for users to voice concerns or report fake reviews. This lack of recourse can lead to frustration and diminish the overall trust in the reputation system.
Powerful pairings

	Reputation + Authority Bias. Combining the power of reputation with the influence of perceived authority can be incredibly persuasive. A financial advisory platform, for example, could highlight its teams qualifications and experience (reputation) and also emphasize endorsements from renowned financial institutions or experts (authority bias).
	Reputation + Value Attribution. Users often attribute value based on external cues. A luxury brand can combine its renowned reputation with premium pricing, leading users to believe that the products value and quality are superior, even if they havent personally experienced the product.
	Reputation + Social Proof + Rewards. By intertwining these three, a platform can enhance its standing. For instance, a fitness app could showcase testimonials of users (Social Proof) who have achieved significant milestones, and then incentivize other users to reach similar milestones with rewards. This not only solidifies the apps reputation for effectiveness but also motivates users to engage more.

### Rationale
Allow users to build reputation by contributing content, sharing information, connecting people, and performing activities that are in line with the purpose of your community. Consider ways to draw in data from external social identities built up on other sites.
Reputation is a powerful determinant in influencing decisions and behaviors. It acts as a heuristic or shortcut for individuals when making choices, especially in situations with limited information or time. A strong reputation can instill trust, reduce perceived risks, and enhance the perceived value of a product or service. Conversely, a negative reputation can deter potential users or customers. Given its influential nature, reputation management has become a focal point for businesses and individuals alike.

### Usage Examples
Reputation is what your audience knows about your knowledge of the subject.
Reputation depends on:

	Achievements or acknowledgments from others in the area, such as, awards and testimonials.
	Your experience and the amount of years you have worked in this area.
	How involved you were with this topic  are you a key character?
	Your expertise should be verified. Have you earned certifications or have other ways of showing off your proven expertise?
	Your contribution to the area, perhaps through blogs, books, papers and products.
	Your authority

Authority and reputation are usually predetermined before your users meet you, why it can be difficult to change the audiences mind about it directly in the situation. However, its easier to change peoples perception about how trustworthy and how alike you are in the situation.

	Let people build reputation. Let users share information, contribute content, connect to other people, keep a record of their personal activities, and perform other activities that are in line with the purpose of your community.
	Encourage wanted behavior. Highlight how specific behavior on your platform can boost reputation growth, access, and capabilities. Similarly, discourage unwanted behavior by either not allowing it or making it harder to perform.
	Promote track record. Provide easy access to testimonials, reviews, accomplishments, papers, and anything that can build on the values of honesty, ethicality, and compassion.

Using Aristotles triad of appeals to communicate Reputation
Reputation is a multifaceted construct, and its influence on persuasion is undeniable. While designers often tap into reputation as a singular entity, breaking it down through the lens of Aristotles triad of appeals – ethos, pathos, and logos – can provide a more nuanced approach to showcasing it.

	Ethos is the foundation of reputation. When designers appeal to ethos, theyre emphasizing the credibility and moral character of an entity. For instance, when a financial platform showcases its certifications and regulatory compliances, its appealing to ethos. Theyre not just showcasing their expertise but emphasizing their commitment to ethical practices and moral values.
	Pathos, on the other hand, brings out the emotional dimension of reputation. A brand or individual might have a stellar reputation, but how does that resonate on an emotional level with the audience? By weaving in a storytelling that evokes emotions, designers can make their reputation efforts more relatable. Consider the story of a brand that started from humble beginnings or an individual user on a platform who overcame significant challenges. These stories dont just highlight achievements; they appeal to the audiences emotions, making the reputation feel more human and rea
	Logos provides the logical backbone to reputation. In showcasing reputation, its crucial to have evidence that supports claims. An e-commerce site, for example, might have a seller with a fantastic reputation. Still, its the detailed product descriptions, transparent customer reviews, and clear return policies that provide the logical evidence supporting this reputation. Its about ensuring that every claim made, every piece of the reputation puzzle, can be backed by clear, logical evidence.

Its multi-dimensional and can be showcased in varied ways by appealing to ethos, pathos, and logos.
Getting a design that showcases reputation right
Reputation, in essence, is a reflection of what your audience knows or believes about your knowledge of a particular subject. Its built on the pillars of achievements, experience, involvement, verified expertise, and significant contributions to a domain.
For instance, the manner in which awards, testimonials, years of experience, and the depth of involvement with a topic can shape the perception of reputation is evident in platforms like LinkedIn, where endorsements and recommendations play a pivotal role. On Stack Overflow, users earn reputation points by providing valuable answers, signaling their expertise and trustworthiness in specific areas.
However, the journey to building and maintaining a robust reputation isnt just about showcasing past accomplishments. Its also about the present actions and the avenues a platform offers for users to shape their reputation. Encouraging users to actively participate, share information, contribute content, and connect with others can be a transformative strategy. Such engagement not only amplifies the sense of community but also lets users carve out their niche, as seen on platforms like Etsy where sellers build their reputation through transparent transaction histories.
While reputation can often precede a users direct interaction with a platform, once theyre engaged, its pivotal to highlight how specific behaviors can enhance their reputation. For instance, platforms like LinkedIn and Etsy have embedded the reputation system within their core, allowing users to understand that responsible and commendable behavior will be rewarded.
Yet, in this endeavor, designers must tread carefully. Its crucial to promote a track record that champions values like honesty, ethicality, and compassion. Easy access to testimonials, reviews, and accomplishments can solidify a users trust. Conversely, designers should be wary of and actively discourage any behavior that might tarnish this trust.
While authority and reputation might be predetermined before users encounter a platform, the design has the power to either reinforce or reshape these notions. By creating avenues for users to build and showcase their reputation, and by emphasizing values that resonate with the audience, designers can craft experiences that are not just engaging but also deeply trustworthy.
Reputation can be a powerful tool. However, there are pitfalls to avoid. One major error is the temptation to artificially inflate reputation, either by purchasing fake reviews or suppressing negative ones. This manipulation can quickly backfire, damaging trust when users discern the inauthenticity. Another common oversight is not providing a platform for users to voice concerns or report fake reviews. This lack of recourse can lead to frustration and diminish the overall trust in the reputation system.
Powerful pairings

	Reputation + Authority Bias. Combining the power of reputation with the influence of perceived authority can be incredibly persuasive. A financial advisory platform, for example, could highlight its teams qualifications and experience (reputation) and also emphasize endorsements from renowned financial institutions or experts (authority bias).
	Reputation + Value Attribution. Users often attribute value based on external cues. A luxury brand can combine its renowned reputation with premium pricing, leading users to believe that the products value and quality are superior, even if they havent personally experienced the product.
	Reputation + Social Proof + Rewards. By intertwining these three, a platform can enhance its standing. For instance, a fitness app could showcase testimonials of users (Social Proof) who have achieved significant milestones, and then incentivize other users to reach similar milestones with rewards. This not only solidifies the apps reputation for effectiveness but also motivates users to engage more.

---

## Retaliation

**URL Validation:** https://ui-patterns.com/patterns/revenge

### Problem Summary
People repay in kind

### Solution
Give before you ask. Demonstrate the value you have to offer before asking users to convert into paying customers. Asking too early can backfire into bad reputation. Start by giving before taking in order to get users to reciprocate.
	Build a relationship first. Asking before providing trust in your intentions can create suspicion and make users reluctant to cooperate.
	Dont be evil. The negative emotional value of a transactional loss of $100 is at least twice as much as the positive emotional value of a $100 gain. Acts of retaliation also tend to be equally larger than acts of positively giving back.

### Rationale
If we feel we have been treated unfairly, we have an urge to want everyone else to know what that person did to us. Loss Aversion plays into this, as we perceive the value of a loss much greater than we do with gains and thus reciprocate more with anger than with joy.
Retaliation refers to the inherent human tendency to respond to actions in a manner that mirrors the nature of the original action, be it positive or negative.
At its core, retaliation is deeply rooted in the principle of reciprocity, but with a focus on responding to perceived slights or negative actions. While reciprocity typically emphasizes the positive cycle of giving and receiving, retaliation underscores the human desire to settle the score when treated unfairly or negatively. This pattern can influence decisions, behaviors, and overall experiences with products or services. However, when tapping into this pattern, its crucial to approach it with care, ensuring that interactions foster a positive user experience and do not instigate negative behaviors or feelings.
The principle underlying retaliation is rooted in the fundamental human desire for fairness and justice. When individuals perceive that they have been treated unfairly, they often respond with actions intended to balance the scales. This drive for equity is deeply embedded in human psychology and can be observed across cultures and contexts.
Retaliation is intricately linked to the principle of Loss Aversion. The pain of a loss (or perceived slight) is often felt more acutely than the pleasure of a gain. This is especially true for retaliation, or negative reciprocity, which carries more emotional weight than positive reciprocity. The urge to set things right after feeling wronged often outweighs the potential benefits of letting go or responding with generosity.

### Usage Examples
Give before you ask. Demonstrate the value you have to offer before asking users to convert into paying customers. Asking too early can backfire into bad reputation. Start by giving before taking in order to get users to reciprocate.
	Build a relationship first. Asking before providing trust in your intentions can create suspicion and make users reluctant to cooperate.
	Dont be evil. The negative emotional value of a transactional loss of $100 is at least twice as much as the positive emotional value of a $100 gain. Acts of retaliation also tend to be equally larger than acts of positively giving back.

---

## Rule Builder

**URL Validation:** https://ui-patterns.com/patterns/rule-builder

### Problem Summary
The user needs to, often repeatedly, conduct a search query based on a custom set of rules

### Solution
Let the user build a dynamic list of rules to narrow down matching results from a dataset. Each rule is represented by a separate line or box and divided from each other vertically.
Any or all
The user must specify whether a rule is needed (AND) or is optional (OR). A common approach to simplify the implementation of this pattern is to provide an option to choose whether all rules chosen should be matched – or just any of the rules.
A more nuanced approach is to allow each rule to be a required match or just an optional match.
Treat each rule type differently?
As the user choses the kind of rule he or she wants to impose, those rules can have very different impacts on what corresponding data needs to be entered for the rule to give meaning.
This is why many rule builders provide smart mini-forms that vary depending on what kind of rule is selected. One rule might impose a text search, wherein options like contains, does not contain, matches, or do not match make sense. Other rules could be to select an option from a dynamic list or to provide numeric- or range inputs.
Adding and removing rules
The smartest feature rule builders provide is to dynamically add and remove rules.
The Add button is typically located either directly under the rules and remains so as new rules are added or removed, or it located alongside the remove rule button. In the case of the latter, this allows for new rules to be inserted directly beneath a desired rule.
Removing a rule is most often allowed at the beginning or end of the line the rule is presented on.

### Rationale
A rule builder allows a user to specify unique conditions to discover and group items across one or more datasets.
The results returned by an active rule can be dynamic in nature as its related datasets change over time. An active rule can trigger a set of actions to be performed when the conditions, criteria and values of the rule are met. Rules sets can be grouped into discrete units and linked together with condition logic to create highly complex rule conditions.

### Usage Examples
Let the user build a dynamic list of rules to narrow down matching results from a dataset. Each rule is represented by a separate line or box and divided from each other vertically.
Any or all
The user must specify whether a rule is needed (AND) or is optional (OR). A common approach to simplify the implementation of this pattern is to provide an option to choose whether all rules chosen should be matched – or just any of the rules.
A more nuanced approach is to allow each rule to be a required match or just an optional match.
Treat each rule type differently?
As the user choses the kind of rule he or she wants to impose, those rules can have very different impacts on what corresponding data needs to be entered for the rule to give meaning.
This is why many rule builders provide smart mini-forms that vary depending on what kind of rule is selected. One rule might impose a text search, wherein options like contains, does not contain, matches, or do not match make sense. Other rules could be to select an option from a dynamic list or to provide numeric- or range inputs.
Adding and removing rules
The smartest feature rule builders provide is to dynamically add and remove rules.
The Add button is typically located either directly under the rules and remains so as new rules are added or removed, or it located alongside the remove rule button. In the case of the latter, this allows for new rules to be inserted directly beneath a desired rule.
Removing a rule is most often allowed at the beginning or end of the line the rule is presented on.

---

## Self-Monitoring

**URL Validation:** https://ui-patterns.com/patterns/self-monitoring

### Problem Summary
Enable users to track the behavior they want to change

### Solution
Make it easy to measure. Eliminate the boring part of measuring and tracking performance or status to make it easier for users to know how well they are performing.
	Make correction easy. Help users adjust their behavior in real time. Heart rate monitors vibrates when your heart beats too fast or too slow to let the user know whether to decrease or increase the level of exertion.
	Infer consequences. Derive inferences about the broader context by combining several source of self-monitoring data and environmental data. An increased heart rate, little sleep, and no sweat might be a sign of mental stress.

### Rationale
Make it easy for users to track performance or status to help them achieve predetermined goals or outcomes. Letting users understand how well they are performing, willl increase the likelihood of continuing to produce the behavior. Self-monitoring can help users learn about themselves and can be intrinsically motivating, but will almost always fail to get people to do things they do not want to do.

### Usage Examples
Make it easy to measure. Eliminate the boring part of measuring and tracking performance or status to make it easier for users to know how well they are performing.
	Make correction easy. Help users adjust their behavior in real time. Heart rate monitors vibrates when your heart beats too fast or too slow to let the user know whether to decrease or increase the level of exertion.
	Infer consequences. Derive inferences about the broader context by combining several source of self-monitoring data and environmental data. An increased heart rate, little sleep, and no sweat might be a sign of mental stress.

---

## Set Completion

**URL Validation:** https://ui-patterns.com/patterns/set-completion

### Problem Summary
We desire collecting all pieces of a set more the closer it is to being complete

### Solution
People really dont like to keep things incomplete.

	Grouping logic matters. A badly designed set can prove annoying or demotivating.
	Keep sets to a manageable size. If the number of tasks required to completeness is prohibitively high, people may decide not to engage at all to avoid anticipated dissatisfaction with partial completion. Find out, on average, how many people usually complete, and then make your set slightly larger than that.
	Add multiple levels of sets. What happens after completion of one set? Consider celebrating the completion and suggesting one or more follow-up paths to embark on.

### Rationale
People are irrationally but effectively motivated by the idea of completing a set, even if it means working harder or spending more money—with no additional reward other than the satisfaction of completion and the relief of avoiding an incomplete set.
Even without other reward than the completion in itself, logically grouping items or tasks together as part of a set motivates people to reach perceived completion points. Logically grouping tasks into sets and keeping sets manageable in size allows for achievable goals and small successes.
Consider how you can have multiple levels of sets and what kind of things or information suggests logically grouped sets and set completion. This principle of completion also applies to other things left incomplete such as puzzles, pictures, or sentences.

### Usage Examples
People really dont like to keep things incomplete.

	Grouping logic matters. A badly designed set can prove annoying or demotivating.
	Keep sets to a manageable size. If the number of tasks required to completeness is prohibitively high, people may decide not to engage at all to avoid anticipated dissatisfaction with partial completion. Find out, on average, how many people usually complete, and then make your set slightly larger than that.
	Add multiple levels of sets. What happens after completion of one set? Consider celebrating the completion and suggesting one or more follow-up paths to embark on.

---

## Settings

**URL Validation:** https://ui-patterns.com/patterns/settings

### Problem Summary
The user needs a central place to indicate preferences for how the application should behave

### Solution
Let users indicate their preferences for how your product should behave. Provide a central place for users to customize your product to their specifications. Keep configurable options well-organized, predictable, and manageable in number. Group and move less important settings to their own screens.
Provide an overview
Let the user be able to quickly understand all available settings and their current values. If there are many settings to comprehend, prioritize the ones most likely to interest users. Group and move less important settings to seperate screens.
Good Defaults
Consider good initial values for preferences  choose the default most users would choose and be neutral and pose little risk.
When to group
To avoid in-comprehensive lists of preferences, consider clustering settings into multiple shorter lists. Good heuristics are (you might change numbers):

	7 or fewer preferences: Don’t group at all.
	9 to 16: Group related settings under two or more section dividers.
	16 or more: Consider constructing subscreens, but keep a consistent terminology in mind: make sure titles of subscreens match the label of the setting which opens it.

### Usage Examples
Let users indicate their preferences for how your product should behave. Provide a central place for users to customize your product to their specifications. Keep configurable options well-organized, predictable, and manageable in number. Group and move less important settings to their own screens.
Provide an overview
Let the user be able to quickly understand all available settings and their current values. If there are many settings to comprehend, prioritize the ones most likely to interest users. Group and move less important settings to seperate screens.
Good Defaults
Consider good initial values for preferences  choose the default most users would choose and be neutral and pose little risk.
When to group
To avoid in-comprehensive lists of preferences, consider clustering settings into multiple shorter lists. Good heuristics are (you might change numbers):

	7 or fewer preferences: Don’t group at all.
	9 to 16: Group related settings under two or more section dividers.
	16 or more: Consider constructing subscreens, but keep a consistent terminology in mind: make sure titles of subscreens match the label of the setting which opens it.

---

## Shaping

**URL Validation:** https://ui-patterns.com/patterns/shaping

### Problem Summary
Successively reinforce approximations to a target behavior

### Solution
Break down target behavior. When engaging in the desired behavior (e.g. talking in front of a big crowd) is too overwhelming, then break it down into smaller bits that start small and progressively build up into more complex behavior that gradually resembles the target behavior.
	Successively approximate. Start small (e.g. just standing on stake, then saying hello) to successively approximate and build up to the final desired behavior.
	Use to increase or decrease target behavior. Introduce rewards to increase a behavior and punishments to decrease a behavior. A reward can both be positive (adding a favorable event or outcome) and negative (removing of unfavorable event or outcome). Similarly can punishments be both positive (add unfavorable event our outcome) or negative (remove favorable event or outcome).

### Rationale
Clearly define a target behavior with your users. Then design a program that rewards any response that in some way resembles the target behavior and gradually moves your reinforcement only to behavior that is closer to the target behavior until the final target behavior is achieved, which then is the only behavior to be rewarded.

### Usage Examples
Break down target behavior. When engaging in the desired behavior (e.g. talking in front of a big crowd) is too overwhelming, then break it down into smaller bits that start small and progressively build up into more complex behavior that gradually resembles the target behavior.
	Successively approximate. Start small (e.g. just standing on stake, then saying hello) to successively approximate and build up to the final desired behavior.
	Use to increase or decrease target behavior. Introduce rewards to increase a behavior and punishments to decrease a behavior. A reward can both be positive (adding a favorable event or outcome) and negative (removing of unfavorable event or outcome). Similarly can punishments be both positive (add unfavorable event our outcome) or negative (remove favorable event or outcome).

---

## Sunk Cost Effect

**URL Validation:** https://ui-patterns.com/patterns/sunk-cost-effect

### Problem Summary
We are hesitant to pull out of something we have put effort into

### Solution
The Sunk Cost Effect can be utilised in product design in several ways.

	Boost upselling. Once users are invested in a subscription-based service they’re more likely to upgrade or make an additional purchase.
	Boost usage. Paying for the right to use a good or service will increase the rate at which the good will be utilised.
	Remind to boost usage. Tired of last minute cancellations? Notify customers about an the event they have booked and its value in its run-up to boost their desire to attend or gift admission to someone else.
	Remind to post-sell. Offer check-up services on durable goods to remind them of what they have already paid to increase post-sell purchases of complimentary goods.

### Rationale
Why are we likely to continue with an investment even if it would be rational to give it up?
One explanation is our loss aversion. The fact that the impact of losses feels much worse to us than the impact of gains – we are much more likely to avoid losses than seek out wins. In this perspective, we might feel that our past investment will be ‘lost’ if we don’t follow through on the decision to continue investing. In this way we end up making a decision based on fear of loosing what we have already spent rather than consider the actual benefits that would be gained if we did not continue our commitment and proceeded with an alternative option.

### Usage Examples
The Sunk Cost Effect can be utilised in product design in several ways.

	Boost upselling. Once users are invested in a subscription-based service they’re more likely to upgrade or make an additional purchase.
	Boost usage. Paying for the right to use a good or service will increase the rate at which the good will be utilised.
	Remind to boost usage. Tired of last minute cancellations? Notify customers about an the event they have booked and its value in its run-up to boost their desire to attend or gift admission to someone else.
	Remind to post-sell. Offer check-up services on durable goods to remind them of what they have already paid to increase post-sell purchases of complimentary goods.

---

## Temptation Bundling

**URL Validation:** https://ui-patterns.com/patterns/temptation-bundling

### Problem Summary
Engaging in hard tasks is more likely when coupled with something tempting

### Solution
Bundle with instantly gratifying wants. Bundle a want activity (e.g. watching the next episode of a habit-forming television show, checking Facebook, receiving a pedicure, eating an indulgent meal) with engagement in a “should” behavior that provides long-term benefits but requires the exertion of willpower (e.g., exercising at the gym, completing a paper review, spending time with a difficult relative) to promote target behavior.
	Geo-fence features to boost attendance. Restricting access to something desirable (for instance a desirable audiobook) only within the compound of a physical event or gym boosts attendance. Unlock the wanted activity by being on the right location.
	Make chores more bearable. Assess what unique, sustainable and meaningful benefits you can use to make complying with work-place practices more attractive. For example, letting the person manning the shared support phone receive a free coffee card for the week.

### Rationale
Bundle something users enjoy with something they dread to push to take action. When struggling to find enough internal motivation to tackle something you hate, an extrinsic reward can be the needed push to stop avoiding the task. Let users do the right thing and reward them for it.

### Usage Examples
Bundle with instantly gratifying wants. Bundle a want activity (e.g. watching the next episode of a habit-forming television show, checking Facebook, receiving a pedicure, eating an indulgent meal) with engagement in a “should” behavior that provides long-term benefits but requires the exertion of willpower (e.g., exercising at the gym, completing a paper review, spending time with a difficult relative) to promote target behavior.
	Geo-fence features to boost attendance. Restricting access to something desirable (for instance a desirable audiobook) only within the compound of a physical event or gym boosts attendance. Unlock the wanted activity by being on the right location.
	Make chores more bearable. Assess what unique, sustainable and meaningful benefits you can use to make complying with work-place practices more attractive. For example, letting the person manning the shared support phone receive a free coffee card for the week.

---

## Testimonials

**URL Validation:** https://ui-patterns.com/patterns/testimonials

### Solution
A formal statement testifying to the quality and trustworthiness of a product.

### Rationale
We tend to trust online reviews and testimonials as much as recommendations from people we know. Whether testimonials are presented with text, video, or include a picture of the senders face, they offer social proof giving your value claims more legitimacy.

### Usage Examples
A formal statement testifying to the quality and trustworthiness of a product.

---

## Undo

**URL Validation:** https://ui-patterns.com/patterns/undo

### Problem Summary
The user wants to revert a mistaken input

### Solution
Allow users to easily reverse their own actions

### Rationale
Users arent perfect  they tend to make mistakes.
Promote safe exploration and playfulness by providing confidence that mistakes arent permanent. Multi-level undo lets users incrementally construct and explore work paths quickly and easily. The more costly it is to lose data, the more important it is to provide the opportunity to undo.

### Usage Examples
Allow users to easily reverse their own actions

---

## Zeigarnik Effect

**URL Validation:** https://ui-patterns.com/patterns/zeigarnik-effect

### Problem Summary
We remember uncompleted or interrupted tasks better than completed ones

### Solution
Break down complex experiences. Split content into smaller parts making each portion easier to digest.
	Indicate progress clearly. Provide a clear indication of progress in order to motivate users to complete the full list of tasks. The task list can originate from a larger broken down task, but also an artificially created list of tasks to complete onboarding or finish setting up the project.
	Reminder to finish. An interrupted or incomplete task leads to a strong motivation to complete the action. Find ways to remind users that they have unfinished business and show them ways to finish it.

### Rationale
The Zeigarnik effect suggests that when we suspend our work on a task to perform unrelated activities, we will remember the details of the first task better than people who complete it without a break.

### Usage Examples
Break down complex experiences. Split content into smaller parts making each portion easier to digest.
	Indicate progress clearly. Provide a clear indication of progress in order to motivate users to complete the full list of tasks. The task list can originate from a larger broken down task, but also an artificially created list of tasks to complete onboarding or finish setting up the project.
	Reminder to finish. An interrupted or incomplete task leads to a strong motivation to complete the action. Find ways to remind users that they have unfinished business and show them ways to finish it.

---


