## Problem 1

**Classification:** recurrence relation

### Tier 1 — Conceptual Nudge
When you have a matrix with a lot of structure (many zeros, repeated pattern), think about how computing the determinant for size n might relate to computing it for smaller sizes. The tridiagonal structure means most cofactors will be simple.

<details>
<summary>Need more help? Click for Tier 2</summary>

### Tier 2 — The Tool
Use cofactor expansion along the first row. Because of the zeros, only the first two terms will contribute. The first cofactor will give you D_{n-1}, but what about the second? Look carefully at the structure of that minor — it's almost tridiagonal but has a special form. This should give you a recurrence relation D_n = a·D_{n-1} + b·D_{n-2}.

</details>

<details>
<summary>Still stuck? Click for Tier 3</summary>

### Tier 3 — The Outline
Let D_n be the determinant. Expanding along the first row: D_n = 2·C_{11} + (-1)·C_{12}, where C_{11} corresponds to deleting row 1 and column 1 (giving D_{n-1}), and C_{12} corresponds to deleting row 1 and column 2. For the second cofactor, the resulting matrix has a special structure: the (1,1) entry is -1, and the rest is (n-2)×(n-2) tridiagonal. Expand along the first column of this to get D_{n-2}. This yields D_n = 2D_{n-1} - D_{n-2}. Compute D_1 = 2, D_2 = 3. The recurrence has characteristic equation r² - 2r + 1 = 0, giving r = 1 (double root). For a double root, the general solution is D_n = (A + Bn)·1^n = A + Bn. Using initial conditions: D_1 = A + B = 2 and D_2 = A + 2B = 3 gives B = 1 and A = 1. Therefore D_n = n + 1.

</details>

<details>
<summary>Show attack plan</summary>

### Attack Plan
1. Let D_n denote the determinant of the n×n tridiagonal matrix with the given pattern
2. Compute D_1 and D_2 by hand to establish base cases
3. Use cofactor expansion along the first row to relate D_n to D_{n-1} and D_{n-2}
4. Solve the resulting linear recurrence relation
5. Verify the formula matches the base cases

</details>

<details>
<summary>Show full solution</summary>

### Solution
Let D_n denote the determinant of the n×n tridiagonal matrix with 2 on the diagonal and -1 on the super- and sub-diagonals.

**Step 1: Base cases**
For n = 1: D_1 = |2| = 2.
For n = 2: D_2 = |2  -1| = 2·2 - (-1)·(-1) = 4 - 1 = 3.
           |-1  2|

**Step 2: Recurrence relation**
For n ≥ 3, expand det along the first row using cofactor expansion:
D_n = 2·C_{11} + (-1)·C_{12} + 0·C_{13} + ... + 0·C_{1n}

where C_{1j} = (-1)^{1+j} det(A_{1j}) is the (1,j)-cofactor.

For C_{11}: deleting row 1 and column 1 leaves the (n-1)×(n-1) tridiagonal matrix of the same form, so C_{11} = (+1)·D_{n-1}.

For C_{12}: deleting row 1 and column 2 leaves an (n-1)×(n-1) matrix of the form:
|-1  0   0  ... 0 |
|-1  2  -1  ... 0 |
| 0 -1   2  ... 0 |
| ⋮  ⋮   ⋮  ⋱  ⋮ |
| 0  0   0  ... 2 |

Expanding this along the first column:
det(A_{12}) = (-1)·M_{11} + (-1)·M_{21} = (-1)·D_{n-2} + (-1)·0 = -D_{n-2}

where M_{11} is the minor obtained by deleting row 1 and column 1 from A_{12}, which gives the (n-2)×(n-2) tridiagonal matrix, hence has determinant D_{n-2}.

Therefore C_{12} = (-1)^{1+2}·(-D_{n-2}) = (-1)·(-D_{n-2}) = D_{n-2}.

Thus: D_n = 2·D_{n-1} + (-1)·D_{n-2} = 2D_{n-1} - D_{n-2}.

**Step 3: Solve the recurrence**
The characteristic equation is r² - 2r + 1 = 0, which factors as (r-1)² = 0.
This gives a double root r = 1.

For a double root, the general solution is D_n = (A + Bn)·1^n = A + Bn.

Using initial conditions:
D_1 = A + B = 2
D_2 = A + 2B = 3

Subtracting: B = 1, so A = 1.

**Step 4: Final answer**
D_n = n + 1.

**Verification:**
D_1 = 1 + 1 = 2 ✓
D_2 = 2 + 1 = 3 ✓
D_3 = 2·3 - 2 = 4 = 3 + 1 ✓

Therefore, the n×n tridiagonal determinant equals **n + 1**.

</details>

---

## Problem 2

**Classification:** direct eigenvalue computation

### Tier 1 — Conceptual Nudge
Think about the range of J: what vectors can J produce as outputs? What is the dimension of this space? This tells you about one eigenvalue immediately. Then think about what happens when you apply J to the all-ones vector.

<details>
<summary>Need more help? Click for Tier 2</summary>

### Tier 2 — The Tool
The matrix J has rank 1 because all rows are identical. By the rank-nullity theorem, the kernel (which is the 0-eigenspace) has dimension n-1. For the non-zero eigenvalue, observe that J times the all-ones vector produces a simple output. Use the formula for the characteristic polynomial in terms of eigenvalues.

</details>

<details>
<summary>Still stuck? Click for Tier 3</summary>

### Tier 3 — The Outline
Write J = vv^T where v = (1,1,...,1)^T. Then Jv = (v^Tv)v = nv, so n is an eigenvalue with eigenvector v. Since rank(J) = 1, we have nullity(J) = n-1, meaning dim(E_0) = n-1. The characteristic polynomial has the form χ_J(x) = x^(n-1)(x-n) since eigenvalues are 0 (multiplicity n-1) and n (multiplicity 1). For diagonalizability, check that dim(E_0) + dim(E_n) = (n-1) + 1 = n, which equals the size of the matrix.

</details>

<details>
<summary>Show attack plan</summary>

### Attack Plan
1. Observe that J can be written as J = vv^T where v is the all-ones vector
2. Use this to directly find an eigenvector for a non-zero eigenvalue
3. Observe that J has rank 1, so nullity is n-1
4. Conclude that 0 is an eigenvalue with geometric multiplicity n-1
5. Compute the characteristic polynomial using rank information
6. Verify diagonalizability by checking if eigenspace dimensions sum to n

</details>

<details>
<summary>Show full solution</summary>

### Solution
Let v = (1,1,...,1)^T ∈ ℝ^n denote the column vector with all entries equal to 1.

**Part (i): Finding eigenvalues and characteristic polynomial**

First, observe that J can be written as J = vv^T (outer product). Each column of J is the vector v.

**Finding the eigenvalue n:**
Compute Jv = (vv^T)v = v(v^Tv) = v · n = nv, since v^Tv = 1 + 1 + ... + 1 = n.
Therefore, v is an eigenvector with eigenvalue λ = n.

**Finding the eigenvalue 0:**
Observe that J has rank 1, since all rows are identical (each row is (1,1,...,1)). By the rank-nullity theorem, dim(ker J) = n - rank(J) = n - 1.

Since ker(J) = {x ∈ ℝ^n : Jx = 0} is precisely the 0-eigenspace E_0, we have that 0 is an eigenvalue with geometric multiplicity (dimension of eigenspace) equal to n - 1.

**Characteristic polynomial:**
The characteristic polynomial is χ_J(x) = det(xI - J). Since J has eigenvalues 0 (with algebraic multiplicity at least n-1) and n (with algebraic multiplicity at least 1), and the algebraic multiplicities must sum to n (the degree of χ_J), we conclude:

χ_J(x) = x^(n-1)(x - n)

This can be verified by expanding: χ_J(x) = x^n - nx^(n-1), which is a monic polynomial of degree n, as expected.

**Part (ii): Finding eigenspaces and checking diagonalizability**

**Eigenspace E_n:**
We need to solve Jx = nx, or equivalently (J - nI)x = 0.
For x = (x_1,...,x_n)^T, we have Jx = (s,s,...,s)^T where s = x_1 + ... + x_n (the sum of all entries).
The equation Jx = nx becomes (s,s,...,s)^T = n(x_1,...,x_n)^T.
This gives s = nx_i for all i, so x_1 = x_2 = ... = x_n = s/n.
Therefore, all entries of x must be equal.

E_n = span{v} = span{(1,1,...,1)^T}

Thus dim(E_n) = 1.

**Eigenspace E_0:**
We need to solve Jx = 0.
For x = (x_1,...,x_n)^T, we have Jx = (s,s,...,s)^T where s = x_1 + ... + x_n.
The equation Jx = 0 requires s = 0, i.e., x_1 + x_2 + ... + x_n = 0.

E_0 = {x ∈ ℝ^n : x_1 + x_2 + ... + x_n = 0}

This is a hyperplane through the origin. To find a basis, we can use:
e_1 - e_n, e_2 - e_n, ..., e_(n-1) - e_n

where e_i is the i-th standard basis vector. These are clearly in E_0 (their coordinates sum to zero) and are linearly independent. Therefore dim(E_0) = n - 1.

**Diagonalizability:**
For J to be diagonalizable, we need the direct sum of eigenspaces to equal ℝ^n.
We have dim(E_0 ⊕ E_n) = dim(E_0) + dim(E_n) = (n-1) + 1 = n.

Since this equals the dimension of ℝ^n, and eigenspaces for distinct eigenvalues form a direct sum, we have:

ℝ^n = E_0 ⊕ E_n

Therefore, **J is diagonalizable**.

Explicitly, J is diagonalizable with diagonal form D = diag(n, 0, 0, ..., 0), achieved by the change of basis consisting of v and any basis for E_0.

</details>

---

## Problem 3

**Classification:** spectral/eigenspace decomposition

### Tier 1 — Conceptual Nudge
The condition S² = I is very restrictive. Think about what happens when you apply S to an eigenvector. How does the relation S² = I constrain the eigenvalue? Once you know all possible eigenvalues, consider how the identity map can be split into two projection operators associated with each eigenvalue.

<details>
<summary>Need more help? Click for Tier 2</summary>

### Tier 2 — The Tool
If Sv = λv, then applying S again gives S²v = λSv = λ²v. But S² = I, so v = λ²v, which means λ² = 1 (since v ≠ 0). This forces λ ∈ {1, -1}. For part (ii), you have two equations: v = u + w and Sv = S(u + w) = Su + Sw = u - w (since u ∈ U and w ∈ W). This is a simple 2×2 linear system. For part (v), recall that a matrix satisfies A^T = A (symmetric) or A^T = -A (skew-symmetric) to be eigenvectors of transpose.

</details>

<details>
<summary>Still stuck? Click for Tier 3</summary>

### Tier 3 — The Outline
Part (i): Let λ be an eigenvalue with eigenvector v. Then S²v = S(Sv) = S(λv) = λSv = λ²v. Since S² = I, we have v = λ²v, so (1 - λ²)v = 0. Since v ≠ 0, we get λ² = 1, giving λ = ±1. Part (ii): From v = u + w and Sv = u - w, add to get 2u = v + Sv, so u = (v + Sv)/2. Subtract to get 2w = v - Sv, so w = (v - Sv)/2. Part (iii): Verify S(u) = S((v + Sv)/2) = (Sv + S²v)/2 = (Sv + v)/2 = u, so u ∈ U. Similarly S(w) = -w. To show V = U ⊕ W, note every v can be written as u + w with this formula, and if u + w = 0 with u ∈ U and w ∈ W, then applying S gives u - w = 0, so u = w = 0. Part (iv): The matrix is block diagonal with an identity block (size dim U) and a negative identity block (size dim W). Part (v): U consists of symmetric matrices A = A^T and W consists of skew-symmetric matrices A = -A^T. A basis for U: the n diagonal matrices E_{ii} plus the (n choose 2) matrices E_{ij} + E_{ji} for i < j. A basis for W: the (n choose 2) matrices E_{ij} - E_{ji} for i < j.

</details>

<details>
<summary>Show attack plan</summary>

### Attack Plan
1. Use S² = I to show that if Sv = λv then λ² = 1, so λ ∈ {1, -1}
2. Assume v = u + w and apply S to get Sv = u - w
3. Solve the 2×2 linear system {v = u + w, Sv = u - w} for u and w
4. Verify the formulas u = (v + Sv)/2 and w = (v - Sv)/2 define elements of U and W
5. Show this decomposition is unique to establish V = U ⊕ W
6. Write S in block diagonal form with respect to eigenbasis
7. For transpose: identify U as symmetric matrices and W as skew-symmetric matrices
8. Construct explicit basis using elementary matrices

</details>

<details>
<summary>Show full solution</summary>

### Solution
**Part (i):** Let λ be an eigenvalue of S with corresponding eigenvector v ≠ 0, so Sv = λv. Applying S to both sides: S²v = S(λv) = λSv = λ(λv) = λ²v. Since S² = I by hypothesis, we have Iv = λ²v, that is, v = λ²v. Rearranging: (1 - λ²)v = 0. Since v ≠ 0 (eigenvectors are nonzero by definition), we must have 1 - λ² = 0, hence λ² = 1. This gives λ = 1 or λ = -1. Therefore **the only possible eigenvalues are 1 and -1**.

**Part (ii):** Suppose v = u + w where u ∈ U and w ∈ W. Since u ∈ U, we have Su = u (u is a 1-eigenvector). Since w ∈ W, we have Sw = -w (w is a (-1)-eigenvector). Applying S to the equation v = u + w:
  Sv = S(u + w) = Su + Sw = u + (-w) = u - w.
Thus we have the system of two equations:
  v = u + w
  Sv = u - w.
Adding these equations: v + Sv = 2u, so **u = (v + Sv)/2**.
Subtracting the second from the first: v - Sv = (u + w) - (u - w) = 2w, so **w = (v - Sv)/2**.

**Part (iii):** We verify that u = (v + Sv)/2 ∈ U and w = (v - Sv)/2 ∈ W.

For u: Apply S to get
  Su = S((v + Sv)/2) = (Sv + S²v)/2.
Since S² = I, we have S²v = Iv = v, so
  Su = (Sv + v)/2 = (v + Sv)/2 = u.
Thus Su = u, which means u ∈ U (u is a 1-eigenvector or u = 0).

For w: Apply S to get
  Sw = S((v - Sv)/2) = (Sv - S²v)/2 = (Sv - v)/2 = -(v - Sv)/2 = -w.
Thus Sw = -w, which means w ∈ W (w is a (-1)-eigenvector or w = 0).

Now we prove **V = U ⊕ W**. We must show:
(1) V = U + W (every vector in V can be written as a sum of elements from U and W).
(2) U ∩ W = {0} (the sum is direct).

For (1): Let v ∈ V be arbitrary. Define u = (v + Sv)/2 and w = (v - Sv)/2. We have just shown that u ∈ U and w ∈ W. Moreover, u + w = (v + Sv)/2 + (v - Sv)/2 = 2v/2 = v. Thus every v ∈ V can be written as u + w with u ∈ U and w ∈ W, so V = U + W.

For (2): Suppose x ∈ U ∩ W. Then x ∈ U means Sx = x, and x ∈ W means Sx = -x. Therefore x = Sx = -x, which gives 2x = 0, hence x = 0. Thus U ∩ W = {0}.

Therefore **V = U ⊕ W**.

**Part (iv):** Let B_U = {u₁, ..., u_k} be a basis for U and B_W = {w₁, ..., w_m} be a basis for W. Consider the ordered basis B = B_U ∪ B_W = {u₁, ..., u_k, w₁, ..., w_m} for V.

For each u_i ∈ B_U, we have Su_i = u_i = 1·u_i (so the coefficient of u_i is 1 and all other coefficients are 0).
For each w_j ∈ B_W, we have Sw_j = -w_j = -1·w_j (so the coefficient of w_j is -1 and all other coefficients are 0).

Therefore the matrix of S with respect to B is
  [S]_B = diag(1, 1, ..., 1, -1, -1, ..., -1)
where there are dim(U) ones followed by dim(W) negative ones. This is a block diagonal matrix:
  **[S]_B = [I_k    0  ]**
          **[0    -I_m]**
where I_k is the k×k identity matrix and I_m is the m×m identity matrix.

**Part (v):** Here V = M_{n×n}(ℝ) and S(A) = A^T (transpose).

First, note that S² = I: S²(A) = S(S(A)) = S(A^T) = (A^T)^T = A, so S² is the identity map.

**U (the 1-eigenspace):** These are matrices A such that S(A) = A, that is, A^T = A. Thus **U is the space of symmetric n×n matrices**.

**W (the (-1)-eigenspace):** These are matrices A such that S(A) = -A, that is, A^T = -A. Thus **W is the space of skew-symmetric (or antisymmetric) n×n matrices**.

Dimension count: dim(U) = n(n+1)/2 (there are n diagonal entries plus (n choose 2) = n(n-1)/2 independent entries above the diagonal). dim(W) = n(n-1)/2 (the diagonal must be zero, and there are (n choose 2) independent entries above the diagonal). Note dim(U) + dim(W) = n(n+1)/2 + n(n-1)/2 = n²/2 + n/2 + n²/2 - n/2 = n² = dim(V), confirming V = U ⊕ W.

**An eigenbasis for S:** We need a basis B_U for U and a basis B_W for W.

Basis for U (symmetric matrices):
- The n matrices E_{ii} for 1 ≤ i ≤ n (diagonal matrices with a single 1 at position (i,i)).
- The n(n-1)/2 matrices E_{ij} + E_{ji} for 1 ≤ i < j ≤ n (symmetric matrices with 1 at positions (i,j) and (j,i)).

Basis for W (skew-symmetric matrices):
- The n(n-1)/2 matrices E_{ij} - E_{ji} for 1 ≤ i < j ≤ n (skew-symmetric matrices with 1 at position (i,j) and -1 at position (j,i)).

Here E_{ij} denotes the matrix with a 1 in position (i,j) and 0 elsewhere.

Thus **B = {E_{ii} : 1 ≤ i ≤ n} ∪ {E_{ij} + E_{ji} : 1 ≤ i < j ≤ n} ∪ {E_{ij} - E_{ji} : 1 ≤ i < j ≤ n}** is an eigenbasis for S, with eigenvalue 1 for the first n(n+1)/2 basis elements and eigenvalue -1 for the last n(n-1)/2 basis elements.

</details>

---

## Problem 4

**Classification:** characteristic polynomial computation and similarity invariants

### Tier 1 — Conceptual Nudge
The characteristic polynomial is a similarity invariant, meaning similar matrices have the same characteristic polynomial. Computing det(A - λI) for each matrix will give you a key piece of information. But be careful: having the same characteristic polynomial doesn't guarantee similarity—you need to check further properties.

<details>
<summary>Need more help? Click for Tier 2</summary>

### Tier 2 — The Tool
Use cofactor expansion to compute det(A - λI). For triangular or near-triangular matrices, the characteristic polynomial can be read almost immediately from the diagonal. For the first and third matrices, expand along a row or column with zeros. Once you have all four polynomials, compare them: if two matrices have different characteristic polynomials, they cannot be similar. If they have the same polynomial, you need to check whether they have the same Jordan normal form or whether they're both diagonalizable with the same eigenspace dimensions.

</details>

<details>
<summary>Still stuck? Click for Tier 3</summary>

### Tier 3 — The Outline
Matrix 1: A - λI has a zero in position (1,3), (2,3). Expand along column 3 to get det(A - λI) = (3-λ) det((2-λ, 6; 1, 1-λ)). The 2×2 determinant is (2-λ)(1-λ) - 6 = λ² - 3λ + 2 - 6 = λ² - 3λ - 4 = (λ-4)(λ+1). So χ₁(λ) = -(λ-3)(λ-4)(λ+1).

Matrix 2: Diagonal matrix with diagonal entries 1, 1, -1. Characteristic polynomial is χ₂(λ) = (1-λ)(1-λ)(-1-λ) = -(1-λ)²(1+λ).

Matrix 3: Expand det(A - λI) = det((-λ, 1, 0; 0, -λ, 1; -1, 1, 1-λ)) along the first row. You get -λ det((-λ, 1; 1, 1-λ)) - 1·det((0, 1; -1, 1-λ)) = -λ(-λ(1-λ) - 1) - (0·(1-λ) + 1) = -λ(-λ + λ² - 1) - 1 = λ² - λ³ + λ - 1. Factor: χ₃(λ) = -λ³ + λ² + λ - 1 = -(λ³ - λ² - λ + 1) = -(λ-1)(λ²-1) = -(λ-1)²(λ+1).

Matrix 4: Upper triangular, so χ₄(λ) = (-1-λ)(3-λ)(4-λ) = -(1+λ)(3-λ)(4-λ) = -(λ+1)(λ-3)(λ-4).

Compare: Matrices 1 and 4 have the same characteristic polynomial (both have eigenvalues -1, 3, 4). Since both have distinct eigenvalues, both are diagonalizable, so they are similar. Matrices 2 and 3 have the same characteristic polynomial χ(λ) = -(1-λ)²(1+λ). Check if they're similar: Matrix 2 is diagonal, so if similar, Matrix 3 must also be diagonalizable. Check the geometric multiplicity of eigenvalue 1 in Matrix 3 by finding dim ker(A₃ - I). If dim = 2, they're similar; if dim = 1, they have different Jordan forms and are not similar.

</details>

<details>
<summary>Show attack plan</summary>

### Attack Plan
1. For each matrix A, compute det(A - λI) by cofactor expansion, choosing the most convenient row or column
2. Simplify each characteristic polynomial to standard form
3. Compare characteristic polynomials: identical polynomials are necessary (but not sufficient) for similarity
4. For matrices with the same characteristic polynomial, check additional invariants such as diagonalizability or geometric multiplicities
5. Conclude which pairs (if any) are similar based on complete invariant matching

</details>

<details>
<summary>Show full solution</summary>

### Solution
Let A₁, A₂, A₃, A₄ denote the four given matrices in order.

**Matrix 1:**
A₁ = [[2, 6, 0], [1, 1, 0], [1, -2, 3]]

We compute det(A₁ - λI):
A₁ - λI = [[2-λ, 6, 0], [1, 1-λ, 0], [1, -2, 3-λ]]

Expanding along the third column (which has two zeros), we get:
det(A₁ - λI) = (3-λ) · det([[2-λ, 6], [1, 1-λ]])
                = (3-λ)[(2-λ)(1-λ) - 6]
                = (3-λ)[2 - 2λ - λ + λ² - 6]
                = (3-λ)[λ² - 3λ - 4]
                = (3-λ)(λ - 4)(λ + 1)

So **χ₁(λ) = -(λ - 3)(λ - 4)(λ + 1)**.

Roots: λ = 3, 4, -1 (all distinct).

**Matrix 2:**
A₂ = [[1, 0, 0], [0, 1, 0], [0, 0, -1]]

This is diagonal, so:
**χ₂(λ) = (1 - λ)(1 - λ)(-1 - λ) = (1 - λ)²(-1 - λ)**

Roots: λ = 1 (multiplicity 2), λ = -1 (multiplicity 1).

**Matrix 3:**
A₃ = [[0, 1, 0], [0, 0, 1], [-1, 1, 1]]

We compute:
A₃ - λI = [[-λ, 1, 0], [0, -λ, 1], [-1, 1, 1-λ]]

Expanding along the first row:
det(A₃ - λI) = -λ · det([[-λ, 1], [1, 1-λ]]) - 1 · det([[0, 1], [-1, 1-λ]]) + 0

det([[-λ, 1], [1, 1-λ]]) = -λ(1-λ) - 1 = -λ + λ² - 1 = λ² - λ - 1

det([[0, 1], [-1, 1-λ]]) = 0·(1-λ) - 1·(-1) = 1

So: det(A₃ - λI) = -λ(λ² - λ - 1) - 1 = -λ³ + λ² + λ - 1

Factoring: -λ³ + λ² + λ - 1 = -(λ³ - λ² - λ + 1) = -(λ²(λ - 1) - (λ - 1)) = -(λ - 1)(λ² - 1) = -(λ - 1)(λ - 1)(λ + 1) = -(λ - 1)²(λ + 1)

So **χ₃(λ) = -(λ - 1)²(λ + 1)**.

Roots: λ = 1 (multiplicity 2), λ = -1 (multiplicity 1).

**Matrix 4:**
A₄ = [[-1, 1, 1], [0, 3, 0], [0, 0, 4]]

This is upper triangular, so the characteristic polynomial is the product of (diagonal entry - λ):
**χ₄(λ) = (-1 - λ)(3 - λ)(4 - λ) = -(λ + 1)(λ - 3)(λ - 4)**

Roots: λ = -1, 3, 4 (all distinct).

**Comparison:**
- χ₁(λ) = -(λ-3)(λ-4)(λ+1) has roots {3, 4, -1} (all distinct)
- χ₂(λ) = -(1-λ)²(1+λ) has roots {1, 1, -1}
- χ₃(λ) = -(1-λ)²(1+λ) has roots {1, 1, -1}
- χ₄(λ) = -(λ+1)(λ-3)(λ-4) has roots {-1, 3, 4} (all distinct)

**Matrices A₁ and A₄ have the same characteristic polynomial!** Both have eigenvalues {-1, 3, 4}, all with multiplicity 1. Since both have distinct eigenvalues, both are diagonalizable. Two diagonalizable matrices with the same eigenvalues and multiplicities are similar. Therefore **A₁ and A₄ are similar**.

**Matrices A₂ and A₃ also have the same characteristic polynomial!** This is necessary but not sufficient for similarity.

**Testing similarity of A₂ and A₃:**

Since A₂ is diagonal (hence diagonalizable), if A₂ and A₃ are similar, then A₃ must also be diagonalizable. A matrix is diagonalizable if and only if for each eigenvalue, its geometric multiplicity equals its algebraic multiplicity.

For A₃:
- Eigenvalue λ = 1 has algebraic multiplicity 2
- Eigenvalue λ = -1 has algebraic multiplicity 1

We need to check the geometric multiplicity of λ = 1, i.e., dim(ker(A₃ - I)).

A₃ - I = [[-1, 1, 0], [0, -1, 1], [-1, 1, 0]]

Row reducing:
[[-1, 1, 0], [0, -1, 1], [-1, 1, 0]] → [[-1, 1, 0], [0, -1, 1], [0, 0, 0]] (subtract row 1 from row 3)

From row 2: -y + z = 0, so z = y.
From row 1: -x + y = 0, so x = y.

So ker(A₃ - I) = {(t, t, t) : t ∈ ℝ} has dimension 1.

Since the geometric multiplicity (1) is less than the algebraic multiplicity (2) for eigenvalue 1, matrix A₃ is NOT diagonalizable.

Since A₂ is diagonalizable but A₃ is not, **A₂ and A₃ are not similar**.

**Conclusion:**
- **A₁ and A₄ are similar** (both diagonalizable with eigenvalues -1, 3, 4)
- A₂ and A₃ have the same characteristic polynomial but are not similar (different Jordan forms)

</details>

---

## Problem 5

**Classification:** polynomial identities and symmetric functions

### Tier 1 — Conceptual Nudge
For part (i), consider what happens to Δ when roots are complex conjugates versus all real. For the later parts, think about what the coefficients of a polynomial tell you about symmetric functions of its roots. The Vandermonde determinant has a standard formula involving differences of roots.

<details>
<summary>Need more help? Click for Tier 2</summary>

### Tier 2 — The Tool
Use Vieta's formulas to relate elementary symmetric functions to coefficients. For the recurrence in part (iv), multiply the equation aᵏ⁺³+maᵏ⁺¹+naᵏ=0 by noting each root satisfies the cubic. For part (v), recognize that det A is a Vandermonde determinant with value (b-a)(c-a)(c-b), and compute A^T A by expanding the (i,j)-entry as Sᵢ₊ⱼ₋₂. The key is that det(A^T A) = (det A)² = Δ.

</details>

<details>
<summary>Still stuck? Click for Tier 3</summary>

### Tier 3 — The Outline
Part (i): Δ is a product of squared terms, so it's real (or note that if complex roots exist, they come in conjugate pairs for real polynomials, making differences conjugate pairs whose product is real). When Δ>0, all roots are real and distinct; Δ=0 means repeated roots; Δ<0 means one real and two complex conjugate roots. Part (ii): Expand (z-a)(z-b)(z-c) = z³-(a+b+c)z²+(ab+bc+ca)z-abc; matching with z³+mz+n gives coefficient of z² is 0, so a+b+c=0; also ab+bc+ca=m and abc=-n. Part (iii): S₀=3, S₁=a+b+c=0, S₂=a²+b²+c²=(a+b+c)²-2(ab+bc+ca)=0-2m=-2m. Part (iv): Since each root satisfies aᵏ⁺³=-maᵏ⁺¹-naᵏ, sum over roots to get Sₖ₊₃=-mSₖ₊₁-nSₖ. Thus S₃=-mS₁-nS₀=-n·3=-3n and S₄=-mS₂-nS₁=-m(-2m)=2m². Part (v): det A = (b-a)(c-a)(c-b) (Vandermonde). A^T A has (i,j) entry equal to Sᵢ₊ⱼ₋₂. So A^T A = [[S₀, S₁, S₂], [S₁, S₂, S₃], [S₂, S₃, S₄]] = [[3, 0, -2m], [0, -2m, -3n], [-2m, -3n, 2m²]]. Compute det(A^T A) = (det A)² = Δ. Expanding this 3×3 determinant and setting equal to Δ yields Δ=-4m³-27n².

</details>

<details>
<summary>Show attack plan</summary>

### Attack Plan
1. Use complex conjugate properties to establish that Δ is real
2. Apply Vieta's formulas to the expanded polynomial (z-a)(z-b)(z-c)
3. Compute power sums using relations from parts (i)-(ii)
4. Establish the recurrence relation by substituting the cubic equation
5. Compute the Vandermonde determinant directly
6. Calculate A^T A explicitly and relate (det A)² to Δ
7. Use the relations from previous parts to express Δ in terms of m, n

</details>

<details>
<summary>Show full solution</summary>

### Solution
**Part (i):** The discriminant Δ=(a-b)²(a-c)²(b-c)² is a product of squared terms, hence non-negative if all factors are real. However, for a cubic with real coefficients m and n, if complex roots exist, they must appear as conjugate pairs. Since we have three roots, either all three are real, or one is real and two are complex conjugates.

If all roots are real, then all differences (a-b), (a-c), (b-c) are real, so Δ is real and non-negative. If a is real and b, c are complex conjugates, write b=p+qi and c=p-qi with q≠0. Then b-c=2qi, so |b-c|²=4q². Also, a-b and a-c are conjugates, so (a-b)(a-c) = |a-b|². Therefore Δ = |a-b|⁴·|a-c|⁴·(4q²)² is real. Moreover, we can verify by expanding that Δ is actually a symmetric polynomial in the roots with real coefficients, hence must be real.

**Sign interpretation:**
- **Δ > 0:** All three roots are real and distinct (all pairwise differences nonzero)
- **Δ = 0:** At least two roots coincide (repeated root)
- **Δ < 0:** One real root and two complex conjugate roots (the product involves conjugate differences)

**Part (ii):** Expand the left side of (z-a)(z-b)(z-c):

(z-a)(z-b)(z-c) = z³ - (a+b+c)z² + (ab+bc+ca)z - abc

Comparing with z³+mz+n (noting there is no z² term), we get:
- Coefficient of z²: -(a+b+c) = 0, therefore **a+b+c = 0**
- Coefficient of z: ab+bc+ca = m, therefore **m = ab+bc+ca**
- Constant term: -abc = n, therefore **n = -abc**

**Part (iii):**
- S₀ = a⁰+b⁰+c⁰ = 1+1+1 = **3**
- S₁ = a+b+c = **0** (from part ii)
- S₂ = a²+b²+c²

To find S₂, use the identity (a+b+c)² = a²+b²+c² + 2(ab+bc+ca):

0 = S₂ + 2m

Therefore **S₂ = -2m**.

**Part (iv):** Each root satisfies the cubic equation. Specifically, for each root r ∈ {a,b,c}:

r³ + mr + n = 0

Multiplying by rᵏ:

rᵏ⁺³ + mrᵏ⁺¹ + nrᵏ = 0

Summing over all three roots:

aᵏ⁺³ + bᵏ⁺³ + cᵏ⁺³ + m(aᵏ⁺¹ + bᵏ⁺¹ + cᵏ⁺¹) + n(aᵏ + bᵏ + cᵏ) = 0

Therefore **Sₖ₊₃ + mSₖ₊₁ + nSₖ = 0** for all k≥0.

Applying this recurrence:

For k=0: S₃ + mS₁ + nS₀ = 0
S₃ + m(0) + n(3) = 0
**S₃ = -3n**

For k=1: S₄ + mS₂ + nS₁ = 0
S₄ + m(-2m) + n(0) = 0
**S₄ = 2m²**

**Part (v):** The matrix A is a Vandermonde matrix:

A = [[1, a, a²],
     [1, b, b²],
     [1, c, c²]]

The determinant of a Vandermonde matrix with rows corresponding to values a, b, c is:

**det A = (b-a)(c-a)(c-b)**

Now compute A^T A. The (i,j)-entry of A^T A equals:

(A^T A)ᵢⱼ = Σₖ Aₖᵢ Aₖⱼ = Σ rₖ^(i-1) rₖ^(j-1) = Σ rₖ^(i+j-2) = Sᵢ₊ⱼ₋₂

where the sum is over the three roots r₁=a, r₂=b, r₃=c.

Therefore:

A^T A = [[S₀, S₁, S₂],
         [S₁, S₂, S₃],
         [S₂, S₃, S₄]]
       = [[3, 0, -2m],
          [0, -2m, -3n],
          [-2m, -3n, 2m²]]

Now det(A^T A) = det(A^T)det(A) = (det A)².

Also, (det A)² = [(b-a)(c-a)(c-b)]² = (b-a)²(c-a)²(c-b)² = (a-b)²(a-c)²(b-c)² = Δ.

So we need to compute det(A^T A) and set it equal to Δ.

Expanding along the first row:

det[[3, 0, -2m],
    [0, -2m, -3n],
    [-2m, -3n, 2m²]]

= 3·det[[-2m, -3n], [-3n, 2m²]] - 0·(...) + (-2m)·det[[0, -2m], [-2m, -3n]]

= 3·[(-2m)(2m²) - (-3n)(-3n)] + (-2m)·[0·(-3n) - (-2m)(-2m)]
= 3·[-4m³ - 9n²] + (-2m)·[0 - 4m²]
= -12m³ - 27n² + (-2m)(-4m²)
= -12m³ - 27n² + 8m³
= -4m³ - 27n²

Therefore **Δ = -4m³ - 27n²**.

</details>

---
