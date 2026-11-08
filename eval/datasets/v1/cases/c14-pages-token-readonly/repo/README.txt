# Handbook publishing

The main branch holds the source page.
The site is copied into the public directory.
The publishing job commits that directory.
It then pushes to the gh-pages branch.
The published branch is configured as the site source.
Change index.html to update the handbook.
The job runs after changes to main.
No generated output is stored on main.
