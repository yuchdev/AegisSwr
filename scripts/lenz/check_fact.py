import argparse
import os

import httpx

# Configuration
BASE_URL = "https://lenz.io/api/v1"
LENZ_API_KEY = os.getenv("LENZ_API_KEY")

# Specialized claims database with expected verdicts
CLAIMS_DB = {
    "ct": {
        "description": "Medical Imaging (PCCT & 7T MRI)",
        "expected": "True",
        "text": (
            "Modern photon-counting detector CT (PCCT) systems achieve spatial resolutions "
            "of approximately 0.2 millimeters by directly converting X-ray photons into "
            "electrical signals without an intermediate scintillation step, whereas "
            "ultra-high-field 7-Tesla MRI systems are currently FDA-cleared exclusively "
            "for imaging the head and extremities due to radiofrequency wavelength limitations "
            "in the human torso."
        ),
    },
    "crispr": {
        "description": "Genomics (CRISPR-Cas Mechanisms)",
        "expected": "True",
        "text": (
            "Cas9 nucleases induce blunt double-strand breaks approximately 3 base pairs "
            "upstream of the Protospacer Adjacent Motif (PAM), whereas Cas12a (Cpf1) "
            "creates staggered cuts leaving 4-5 nucleotide 5' overhangs distal to its "
            "T-rich PAM."
        ),
    },
    "quantum": {
        "description": "Quantum Computing (Shor's Algorithm)",
        "expected": "True",
        "text": (
            "Shor's algorithm achieves a polynomial time complexity of O((log N)^3) for "
            "prime factorization, offering an exponential speedup over the best known "
            "classical algorithm, the General Number Field Sieve (GNFS), which operates "
            "in sub-exponential time."
        ),
    },
    "graphene": {
        "description": "Materials Science (Graphene Electronics)",
        "expected": "True",
        "text": (
            "Graphene exhibits an anomalous Quantum Hall Effect at room temperature due "
            "to its massless Dirac fermions, but lacks a natural bandgap, which strictly "
            "limits its direct application in conventional CMOS digital logic circuits "
            "without chemical functionalization or nanoribbon patterning."
        ),
    },
    "neuro": {
        "description": "Neurobiology (Optogenetics)",
        "expected": "False",  # Intentionally false to test negative detection
        "text": (
            "Optogenetics relies exclusively on channelrhodopsin-2 (ChR2), which actively "
            "pumps chloride ions into neurons upon blue light illumination (470 nm), "
            "resulting in robust membrane hyperpolarization and rapid silencing of action potentials."
        ),  # Fact check: ChR2 is a cation channel that DEPOLARIZES (excites). Halorhodopsin pumps chloride.
    },
}


def check_fact(claim_key: str):
    """Assess a single claim from ``CLAIMS_DB`` via the lenz.io API and print the verdict.

    Requires the ``LENZ_API_KEY`` environment variable; fails fast when it is
    unset rather than sending an unauthenticated request.
    """
    if not LENZ_API_KEY:
        raise RuntimeError("LENZ_API_KEY environment variable is not set")
    headers = {"Authorization": f"Bearer {LENZ_API_KEY}"}

    claim_data = CLAIMS_DB[claim_key]
    print(f"--- Running Claim: {claim_key.upper()} ({claim_data['description']}) ---")
    print(f"Claim Text: {claim_data['text']}\n")

    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{BASE_URL}/assess",
                headers=headers,
                json={"claim": claim_data["text"]},
            )
            r.raise_for_status()

            response_data = r.json()
            claims_results = response_data.get("claims", [])

            if not claims_results:
                print("Error: API returned no claims in the response.")
                return

            for idx, result in enumerate(claims_results, 1):
                api_verdict = str(result.get("verdict", "Unknown"))
                confidence = result.get("confidence", 0.0)

                # Check if API verdict matches our expected verdict
                match = api_verdict.lower() == claim_data["expected"].lower()
                status_badge = "[PASS]" if match else "[FAIL]"

                print(f"Result {idx}:")
                print(f"  Expected Verdict : {claim_data['expected']}")
                print(f"  API Verdict      : {api_verdict} {status_badge}")
                print(f"  Confidence       : {confidence}")
                print("-" * 50)

    except httpx.HTTPError as e:
        print(f"HTTP Exception occurred: {e}")
    except ValueError as e:
        print(f"An error occurred: {e}")


def main():
    """Parse the claim-selection CLI argument and run :func:`check_fact` for it."""
    parser = argparse.ArgumentParser(description="Test lenz.io fact-checking API with specialized claims.")

    # Create a list of available choices based on dictionary keys
    choices = list(CLAIMS_DB.keys())

    parser.add_argument(
        "claim_name",
        type=str,
        choices=choices,
        help=f"The ID of the claim to test. Available options: {', '.join(choices)}",
    )

    args = parser.parse_args()
    check_fact(args.claim_name)


if __name__ == "__main__":
    main()
