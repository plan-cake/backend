# plancake Backend

The API for the scheduling platform *plancake*.

## Project Setup
*(Run all commands from the root directory)*

- Set up a Python virtual environment (optional, but highly recommended)
- Install packages with `pip install -r requirements.txt`
- Set up a PostgreSQL database (local works fine, otherwise [Supabase](https://supabase.com) offers free remote database hosting)

### `.env` File
Copy the contents of `example.env` into a new file called `.env` in the same directory.
- Replace fields with relevant information for your environment
    - `DB_`-prefixed variables are for database authentication info
    - `AWS_SES_`-prefixed variables, `DEFAULT_FROM_EMAIL`, and `BASE_URL` are only needed if `SEND_EMAILS` is set to `True`

### Database Migrations
The project contains a database model that determines the structure of the connected database. When it gets changed, Django's "migrations" feature keeps development databases up to date on these changes.
- Apply these migrations with `python manage.py migrate` when you first set up the project
- Make sure to also run this command whenever you pull changes from another branch

### Running the Server
After the above steps, run the server with `python manage.py runserver`

### *(Optional for Development)* Automated Tasks
This project uses Celery and Redis to automate tasks like cleaning up old sessions.

First, Redis needs to be installed and run as a service.
- `sudo apt update`
- `sudo apt install redis-server`
- `sudo service redis-server start`
    - *This might need to be called any time you start your machine*

To run Celery alongside the API server (in different terminals):
- `celery -A api worker --loglevel=info`
- `celery -A api beat --loglevel=info`

## Best Practices
Here at Plancake Industries, we have a strict set of guidelines to follow when contributing to this project to keep a clean, maintainable codebase. Product quality is of utmost importance for any contribution, no matter the size.

Violating any of our guidelines may subject you to circumstances including but not limited to:
- A slap on the wrist
- The end of the world
- A fine of two (2) doubloons
- Demotion
- Promotion
- A call home to your mother
- Literally nothing

### Project Title
For all intents and purposes, the full and exact name of this project is "The Modular, Scalable, Easy to Work With Backend".
- Anything less would be an insult to the countless hours of research and development put into this project.
- Anything more would be untruthful. Here at Plancake Industries, we pride ourselves on being honest and transparent with our investors and userbase. Overpromising and underdelivering are the last things we would ever want to do.

<sub>*The name of this repository was not our choice. IT declined our request for a name change because it was "too long" and "irrelevant".*</sub>

### DRY (Don't Repeat Yourself)
One of the core principles that we live and breathe here at Plancake Industries is DRY. Creating modular code is essential for the maintainability of a large-scale project. DRY has the following benefits:
- Consistent behavior across various sections of code.
- Reduced typos and mistakes in areas with identical logic.
- Core logic only needs to be changed in one place.
- Breaking the code in one place breaks it ***EVERYWHERE!***

Any contributor caught telling the same story on different occasions will be in violation of our guidelines.

### Decorators
In this project, decorators are your best friend! They allow you to easily add functionality to methods without writing additional code inside of them.

Here are some things that decorators can do:
- Validate input/output format
- Check for user authentication
- Modify or add arguments
- Fold your laundry
- Feed your kids
- Pay your taxes
- Apply rate limits

For example:
```python
@fold_laundry("Shirts")
def login(request):
    do_login()
```

In this scenario, every time you call `login` it will also run whatever code exists in `fold_laundry`. The laundry can be folded either before or after the login happens, depending on the implementation.

After folding the shirts, they can be added to the `request` argument, in a `closet` property. Alternatively, the decorator could completely change the return value to be a list of the shirts that were just folded.

Or... let's say all the laundry is already folded. When calling `login`, the decorator could stop before even reaching the code in `login` and pre-emptively return an error message.

The possibilities are endless!

In this project, **the order in which you add your decorators matters**. As long as you follow existing endpoints, you should be fine. Mainly, just make sure that `@api_endpoint` is the outermost decorator.

### Logging
They say information is half the battle. Here at Plancake Industries, we don't often end up in war, but we still like having information.

We take advantage of Python's built-in `logging` module to keep track of information during the execution of API logic. If something goes wrong, any information is good information.

There are 5 levels of log severity:
- `DEBUG` - Use this to log variable values, or any information that might be useful in the case of an error.
- `INFO` - This can just document logic flow, marking milestones in an endpoint before something might go wrong.
- `WARNING` - A potential problem. Either not a big deal, or something that could be a problem later.
- `ERROR` - A non-insignificant problem. Not the end of the world, but worth getting attention at some point.
- `CRITICAL` - Something is VERY wrong. Someone needs to know about this immediately.

Using the logger is simple:
```python
import logging

logger = logging.getLogger("api")

logger.debug("Just nuked the database!")
logger.info("And all the backups!")
```
> ***IMPORTANT - Make sure you use `logger.debug` instead of `logging.debug`. It's a very easy mistake to make, and will result in no information being captured.***

Also, make sure not to log sensitive user information, such as passwords.

Unfortunately, there is such a thing as too much logging. At some point, it will slow down code execution and  quickly fill up disk space. Log anything that would be relevant if a bug appears.

As said before, just follow existing code and you'll be fine.

### Documentation
Here at Plancake Industries, we think good documentation is the secret to younger-looking skin.

There are two aspects to this:
- Inline comments - Eliminate wrinkles
- Docstrings - Keep your skin clear

The utility of inline comments should be obvious. It helps you understand your code when you forget how it works after just one week. It also allows anyone curious enough to poke around your code and figure out what's going on when you write a disgusting one-liner.

Docstrings are more important, because they directly contribute to our built-in API docs. Our `/docs/` endpoint reads every endpoint, reads metadata from decorators **and docstrings**, and uses that to dynamically create documentation.

We elected to create our own custom documentation instead of using something "built-in" and "easy to use" like Swagger. Here at Plancake Industries, we like to think outside of the box, innovate, and make our lives harder instead of settling for the baseline.

<sub>Jokes aside, Swagger is great. Our stuff is just in a format that wouldn't work with it.</sub>

Docstrings are important not just for backend developers, but also frontend developers (and potentially API abusers) to understand what each function and endpoint does.

*Just remember, well-documented code could keep you looking 20 at 80!*<sup>[Citation needed.]</sup>

### Summary
All of us here at Plancake Industries would like to thank you for your continued support. Feel free to ask any clarifying questions about our policies, but please keep in mind that our response time may vary between 2 and 2,000 business days.

We look forward to seeing your future contributions reside in branch purgatory, never to be merged into main!
