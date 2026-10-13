(define-module (gdnasynth)
  #:use-module (guix gexp)
  #:use-module (guix utils)
  #:use-module (guix packages)
  #:use-module (guix git-download)
  #:use-module (guix build-system pyproject)

  #:use-module (gnu packages check)
  #:use-module (gnu packages python-web)
  #:use-module (gnu packages python-xyz)
  #:use-module (gnu packages engineering)
  #:use-module (gnu packages python-check)
  #:use-module (gnu packages python-build)

  #:use-module (gdnasynth packages python))

(define-public gdnasynth
  (package
    (name "gdnasynth")
    (version "0.1.0")
    (source (local-file ".."
                        "gfet-microfluidics-experiments-checkout"
                        #:recursive? #t
                        #:select? (or (git-predicate (dirname (current-source-directory)))
                                      (const #t))))
    (build-system pyproject-build-system)
    (native-inputs
     (list python-mypy
           python-pylint
           python-pytest
           python-typing-extensions))
    (propagated-inputs
     (list python-requests
           python-pyserial
           python-py-gnuplot
           python-keithley2600))
    (home-page "https://github.com/livingcodeslab/gfet-microfluidics-experiments")
    (synopsis "Guided DNA Synthesis experiments and projects")
    (description
     "This contains the experiments and mini-projects that make up the Guided
 DNA Synthesis project.")
    (license #f)))


gdnasynth
