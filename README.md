# gfet-microfluidics-experiments
Experimental code to run a variety of tests against graphene field-effect transistors (GFET)


## Development

We use GNU Guix to manage the dependencies of this repository.

Clone this repository somewhere on your computer:

```sh
git clone https://github.com/livingcodeslab/gfet-microfluidics-experiments.git
```

change the working directory to the root of the repository

```sh
cd gfet-microfluidics-experiments
```

acquire a guix shell

```sh
guix shell --load-path="$(pwd)/.guix" --container --network --development --file=guix.scm
```

run tests with

```sh
python3 -m pytest
```
