(define-module (gdnasynth packages python)
  #:use-module (guix packages)
  #:use-module (guix download)
  #:use-module (guix build-system pyproject)

  #:use-module (gnu packages python-build)
  #:use-module (gnu packages python-science))


(define-public python-py-gnuplot
  (package
    (name "python-py-gnuplot")
    (version "1.3.2")
    (source
     (origin
       (method url-fetch)
       (uri (pypi-uri "py_gnuplot" version))
       (sha256
        (base32 "0gak2slzdvbmb9nmam7yw639crvxvhwdigw4h57qi06p1szslm8w"))))
    (build-system pyproject-build-system);; probably uses older python-build-system
    (arguments
     (list
      ;; error: invalid command 'test'
      ;; error: in phase 'check': uncaught exception:
      ;; %exception #<&invoke-error program: "python" arguments: ("setup.py" "test" "-v") …
      #:tests? #f))
    (propagated-inputs (list python-pandas))
    (native-inputs (list python-setuptools))
    (home-page "https://www.gnuplot.info")
    (synopsis "py-gnuplot is a python plot tools based on gnuplot.")
    (description "py-gnuplot is a python plot tools based on gnuplot.")
    (license #f)))
