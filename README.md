# [The Faded Parsons Element](https://github.com/ace-lab/faded-parsons-element)
This repository contains the Berkeley Faded Parson's element and is designed to be used as a submodule.

## Adding to Your Projects

This command will add the element to your project in the **properly-named** directory for PrairieLearn to use this element.
``` bash
git submodule add https://github.com/ace-lab/faded-parsons-element.git ./elements/pl-faded-parsons/
```

The main branch is the most recent public release.

## Pulling Changes into Your Projects

As detailed [in the "Working on a Project with Submodules" section of the git book](https://git-scm.com/book/en/v2/Git-Tools-Submodules), pulling must be done with a different command.

From the top-level of your directory run:
``` bash
git submodule update --remote ./elements/pl-faded-parsons/
```
