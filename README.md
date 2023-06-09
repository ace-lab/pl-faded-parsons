# [The Faded Parsons Element](https://github.com/ace-lab/pl-faded-parsons)
This repository contains the Berkeley Faded Parson's element and is designed to be used as a submodule.
**Note, however, that the PrairieLearn server doesn't handle submodules properly when syncing a GitHub repo,**
so to use this in a course, either the course's `elements/` subdirectory will need to contain a **copy** of this repo,
or the top-level `elements/` directory of the PrairieLearn build itself will need a copy of it.

## Adding to Your Projects (for development only)

This command will add the element to your project in the **properly-named** directory for PrairieLearn to use this element.
``` bash
git submodule add https://github.com/ace-lab/pl-faded-parsons.git ./elements/pl-faded-parsons/
```

The main branch is the most recent public release.

## Pulling Changes into Your Projects

As detailed [in the "Working on a Project with Submodules" section of the git book](https://git-scm.com/book/en/v2/Git-Tools-Submodules), pulling must be done with a different command.

From the top-level of your directory run:
``` bash
git submodule update --remote ./elements/pl-faded-parsons/
```
