from ripple.sections import concentration_sentences, cut

TOC = "Table of Contents\nItem 1. Business 4\nItem 1A. Risk Factors 10\nItem 1B. Unresolved 20\nItem 2. Properties 21\n"
BODY_1 = "Item 1. Business\n" + ("We design memory chips. " * 30) + "\nOur products are manufactured by TSMC under contract.\n"
BODY_1A = "Item 1A. Risk Factors\n" + ("Risks exist. " * 40) + "\nWe rely on a single source supplier for substrates, which accounted for 40% of purchases.\n"
TAIL = "Item 1B. Unresolved Staff Comments\nNone.\nItem 2. Properties\nWe own fabs in Idaho.\n"


def test_cut_10k_skips_table_of_contents():
    sections = cut(TOC + BODY_1 + BODY_1A + TAIL, "10-K")
    assert sections["item_1"].startswith("Item 1. Business\nWe design")
    assert "manufactured by TSMC" in sections["item_1"]
    assert "Risk Factors" not in sections["item_1"]
    assert sections["item_1a"].startswith("Item 1A. Risk Factors\nRisks")
    assert "Idaho" not in sections["item_1a"]


def test_concentration_sentences():
    text = ("Customer A accounted for 18% of net revenue in fiscal 2026. The weather was nice. "
            "We depend on a limited number of suppliers for HBM. Interest rates rose by 2%.")
    out = concentration_sentences(text).split("\n")
    assert out == ["Customer A accounted for 18% of net revenue in fiscal 2026.",
                   "We depend on a limited number of suppliers for HBM."]


def test_cut_20f_uses_item_4_and_risk_factors():
    text = ("ITEM 3. KEY INFORMATION\nA. Selected data\n" + "x " * 50 + "\nD. Risk Factors\n" + "Risk text. " * 40 +
            "\nITEM 4. INFORMATION ON THE COMPANY\n" + "We make chips for customers. " * 20 +
            "\nITEM 4A. UNRESOLVED STAFF COMMENTS\nNone.\nITEM 5. OPERATING\n")
    s = cut(text, "20-F")
    assert s["item_1"].startswith("ITEM 4. INFORMATION ON THE COMPANY")
    assert s["item_1a"].startswith("D. Risk Factors")
