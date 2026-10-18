# Interview notes

Questions an interviewer could ask about this project. Fill in **My answer**
in your own words at the end of each milestone. If you can't answer one
without looking at the code, that's a signal to reread that part.

## Milestone 1: audit

**Q1. What was the most serious problem you found, and how did you find it?**
My answer:

**Q2. Your API had an API key. Why wasn't that enough to protect it?**
My answer:

**Q3. Which endpoint is the most dangerous, and why?** (the milestone 1
exercise)
My answer:

**Q4. How did you separate findings you verified from ones you only read in
the code? Why does that matter?**
My answer:

**Q5. A `PATCH` with `{"company": null}` returned 500. Walk through why.**
My answer:

**Q6. Why does an LLM endpoint need limits that a normal CRUD endpoint might
not?**
My answer:

**Q7. What did you decide not to fix, and why?**
My answer:

## Milestone 2: tests first

**Q8. What's a contract (or characterization) test, and why write them
before changing code?**
My answer:

**Q9. How do you know a test can actually catch a bug?** (Hint: what
happened when the list order was flipped to ascending?)
My answer:

**Q10. Why did the `PATCH null` test fail with a database error instead of
`assert 500 == 422`?**
My answer:

**Q11. Why mark the failing test `xfail(strict=True)` instead of leaving it
red, or skipping it? What does `strict` add?**
My answer:

**Q12. Why move `fake_tailoring` into `conftest.py` instead of copying it?**
My answer:

## Milestone 3: idempotency

**Q13. What does "idempotent" mean? Which HTTP methods are idempotent by
design, and why isn't POST?**
My answer:

**Q14. Why do payment APIs and job-queue APIs need idempotency keys?** Give
a concrete failure story for each.
My answer:

**Q15. Why use an Idempotency-Key header instead of a unique constraint on
(company, role)?**
My answer:

**Q16. Two requests with the same key arrive at the same moment. Walk
through exactly what stops both from creating a record.**
My answer:

**Q17. Why is only a successful response stored, and not a failed one?**
My answer:

**Q18. Why does the tailor page change its key when the job description is
edited?**
My answer:

**Q19. What are the limits of this design?** (Think: keys stored forever, no
users, holding a transaction open during the LLM call.)
My answer:
