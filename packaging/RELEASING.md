# Packaging & Versioning
Bumping versions is done with the `bumpver` command, which will be installed as part of the `requirements-dev.txt` file. Bumpver will check the repository to make sure all build versions continue to increment properly.

If you're doing the first commit for a build that will be a new version, you need to specify what kind of release it's going to be (major, minor, or patch).
```
bumpver update --patch
```

Once a version has been updated for the new release, subsequent builds can be done **without** specifying the kind of release, and the build number will be incremented automatically
```
bumpver update
```