"""Phone-line accuracy harness for Pashyanti.

    degrade.py  clean audio -> what a phone line does to it (pure numpy)
    wer.py      Indic-aware normalisation, WER and CER (pure)
    corpus.py   reference clips synthesised from known text, cached
    cli.py      run the comparison and write the report

The point is one honest number: what Prisma v3.0 costs you on 8 kHz µ-law at
a given noise level, measured against its own clean-audio result.
"""
