import json
import os
import secrets
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Flask, request, render_template_string

app = Flask(__name__)
used_confirmations = set()
API_VERSION = "2026-07"

# Load Shopify settings from environment variables or local .env
env = {}

if Path(".env").exists():
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if "=" in line:
                key, value = line.split("=", 1)
                env[key] = value

STORE = os.environ.get("SHOPIFY_STORE", env.get("SHOPIFY_STORE"))
CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", env.get("SHOPIFY_CLIENT_ID"))
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", env.get("SHOPIFY_CLIENT_SECRET"))


def get_access_token():
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }).encode()

    response = urllib.request.urlopen(
        f"https://{STORE}/admin/oauth/access_token",
        data=data
    )

    return json.loads(response.read())["access_token"]


def graphql(token, query, variables):
    body = json.dumps({
        "query": query,
        "variables": variables,
    }).encode()

    req = urllib.request.Request(
        f"https://{STORE}/admin/api/{API_VERSION}/graphql.json",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())


def get_gift_card(token, gift_card_id):
    query = """
    query GetGiftCard($id: ID!) {
      giftCard(id: $id) {
        id
        lastCharacters
        balance {
          amount
          currencyCode
        }
      }
    }
    """

    return graphql(token, query, {"id": gift_card_id})


def list_gift_cards(token):
    query = """
    query GiftCardList {
      giftCards(first: 50, query: "status:enabled") {
        nodes {
          id
          lastCharacters
          balance {
            amount
            currencyCode
          }
        }
      }
    }
    """

    return graphql(token, query, {})


def credit_gift_card(token, gift_card_id, amount, currency):
    mutation = """
    mutation GiftCardCredit(
      $id: ID!,
      $creditInput: GiftCardCreditInput!
    ) {
      giftCardCredit(
        id: $id,
        creditInput: $creditInput
      ) {
        giftCardCreditTransaction {
          id
          amount {
            amount
            currencyCode
          }
          giftCard {
            id
            balance {
              amount
              currencyCode
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "id": gift_card_id,
        "creditInput": {
            "creditAmount": {
                "amount": str(amount),
                "currencyCode": currency,
            },
            "note": "Manual credit - Sukurai Gift Card Manager Web",
        },
    }

    return graphql(token, mutation, variables)


def debit_gift_card(token, gift_card_id, amount, currency):
    mutation = """
    mutation GiftCardDebit(
      $id: ID!,
      $debitInput: GiftCardDebitInput!
    ) {
      giftCardDebit(
        id: $id,
        debitInput: $debitInput
      ) {
        giftCardDebitTransaction {
          id
          amount {
            amount
            currencyCode
          }
          giftCard {
            id
            balance {
              amount
              currencyCode
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "id": gift_card_id,
        "debitInput": {
            "debitAmount": {
                "amount": str(amount),
                "currencyCode": currency,
            },
            "note": "Manual debit - Sukurai Gift Card Manager Web",
        },
    }

    return graphql(token, mutation, variables)


HTML = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>Sukurai Gift Card Manager</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #f6f6f7;
            margin: 0;
            padding: 40px 20px;
            color: #202223;
        }

        .container {
            max-width: 650px;
            margin: 0 auto;
        }

        .card {
            background: white;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 28px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }

        h1 {
            margin-top: 0;
        }

        label {
            display: block;
            font-weight: bold;
            margin-top: 18px;
            margin-bottom: 6px;
        }

        input {
            width: 100%;
            padding: 12px;
            box-sizing: border-box;
            border: 1px solid #bbb;
            border-radius: 8px;
            font-size: 16px;
        }

        button {
            margin-top: 20px;
            padding: 12px 18px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            background: #111;
            color: white;
        }

        .secondary {
            background: #666;
        }

        .info {
            margin-top: 20px;
            padding: 16px;
            background: #f3f3f3;
            border-radius: 8px;
        }

        .success {
            margin-top: 20px;
            padding: 16px;
            background: #e8f5e9;
            border-radius: 8px;
        }

        .error {
            margin-top: 20px;
            padding: 16px;
            background: #fdecea;
            border-radius: 8px;
        }

        .warning {
            margin-top: 20px;
            padding: 16px;
            background: #fff4e5;
            border-radius: 8px;
        }

        .row {
            display: flex;
            justify-content: space-between;
            gap: 20px;
            margin: 8px 0;
        }

        .buttons {
            display: flex;
            gap: 10px;
        }

        a {
            text-decoration: none;
        }
    </style>
</head>
<body>
<div class="container">
    <div class="card">
        <h1>Sukurai Gift Card Manager</h1>

        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}

        {% if success %}
        <div class="success">
            <strong>SUCCESS</strong>
            <div class="row">
                <span>{{ "Added" if balance_action == "add" else "Subtracted" }}</span>
                <span>${{ added }} {{ currency }}</span>
            </div>
            <div class="row">
                <span>New balance</span>
                <span>${{ final_balance }} {{ currency }}</span>
            </div>
            <div class="row">
                <span>Transaction ID</span>
                <span>{{ transaction_id }}</span>
            </div>
        </div>

        <p><a href="/">Start another transaction</a></p>

        {% elif stage == "lookup" %}

        <form method="post">
            <input type="hidden" name="action" value="lookup">

            <label>Select Gift Card</label>
            <select name="gift_card_id" required>
                {% for card in gift_cards %}
                <option value="{{ card.numeric_id }}">
                    **** {{ card.last_chars }} — ${{ card.balance }} {{ card.currency }}
                </option>
                {% endfor %}
            </select>

            <button type="submit">Continue</button>
        </form>

        {% elif stage == "amount" %}

        <div class="info">
            <div class="row">
                <span>Gift Card</span>
                <strong>**** {{ last_chars }}</strong>
            </div>
            <div class="row">
                <span>Current balance</span>
                <strong>${{ current_balance }} {{ currency }}</strong>
            </div>
        </div>

        <form method="post">
            <input type="hidden" name="action" value="review">
            <input type="hidden" name="gift_card_id" value="{{ numeric_id }}">
            <input type="hidden" name="last_chars" value="{{ last_chars }}">
            <input type="hidden" name="current_balance" value="{{ current_balance }}">
            <input type="hidden" name="currency" value="{{ currency }}">
        <input type="hidden" name="confirmation_token" value="{{ confirmation_token }}">

            <label>Balance action</label>
            <select name="balance_action" required>
                <option value="add">Add Balance</option>
                <option value="subtract">Subtract Balance</option>
            </select>

            <label>Amount</label>
            <input
                type="number"
                name="amount"
                min="0.01"
                step="0.01"
                placeholder="Example: 25.00"
                required
            >

            <button type="submit">Review</button>
        </form>

        {% elif stage == "confirm" %}

        <div class="warning">
            <strong>Confirm this balance change</strong>

            <div class="row">
                <span>Gift Card</span>
                <span>**** {{ last_chars }}</span>
            </div>

            <div class="row">
                <span>Current balance</span>
                <span>${{ current_balance }} {{ currency }}</span>
            </div>

            <div class="row">
                <span>{{ "Add amount" if balance_action == "add" else "Subtract amount" }}</span>
                <span>${{ amount }} {{ currency }}</span>
            </div>

            <div class="row">
                <span>New balance</span>
                <strong>${{ new_balance }} {{ currency }}</strong>
            </div>
        </div>

        <form method="post">
            <input type="hidden" name="action" value="{{ 'credit' if balance_action == 'add' else 'debit' }}">
            <input type="hidden" name="gift_card_id" value="{{ numeric_id }}">
            <input type="hidden" name="amount" value="{{ amount }}">
            <input type="hidden" name="currency" value="{{ currency }}">
            <input type="hidden" name="confirmation_token" value="{{ confirmation_token }}">

            <div class="buttons">
                <a href="/">
                    <button type="button" class="secondary">Cancel</button>
                </a>
                <button type="submit">Confirm Add Balance</button>
            </div>
        </form>

        {% endif %}
    </div>
</div>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        try:
            token = get_access_token()
            result = list_gift_cards(token)

            if result.get("errors"):
                raise Exception(result["errors"][0]["message"])

            nodes = result.get("data", {}).get("giftCards", {}).get("nodes", [])

            gift_cards = []
            for card in nodes:
                gift_cards.append({
                    "numeric_id": card["id"].split("/")[-1],
                    "last_chars": card["lastCharacters"],
                    "balance": f'{Decimal(card["balance"]["amount"]):.2f}',
                    "currency": card["balance"]["currencyCode"],
                })

            return render_template_string(
                HTML,
                stage="lookup",
                error=None,
                success=False,
                gift_cards=gift_cards,
            )

        except Exception as e:
            return render_template_string(
                HTML,
                stage="lookup",
                error=f"Could not load Gift Cards: {e}",
                success=False,
                gift_cards=[],
            )

    action = request.form.get("action")

    try:
        token = get_access_token()
    except Exception as e:
        return render_template_string(
            HTML,
            stage="lookup",
            error=f"Could not connect to Shopify: {e}",
            success=False,
        )

    if action == "lookup":
        numeric_id = request.form.get("gift_card_id", "").strip()

        if not numeric_id.isdigit():
            return render_template_string(
                HTML,
                stage="lookup",
                error="Gift Card ID must contain numbers only.",
                success=False,
            )

        gift_card_id = f"gid://shopify/GiftCard/{numeric_id}"

        result = get_gift_card(token, gift_card_id)

        if result.get("errors"):
            return render_template_string(
                HTML,
                stage="lookup",
                error=result["errors"][0]["message"],
                success=False,
            )

        card = result.get("data", {}).get("giftCard")

        if not card:
            return render_template_string(
                HTML,
                stage="lookup",
                error="Gift Card not found.",
                success=False,
            )

        return render_template_string(
            HTML,
            stage="amount",
            error=None,
            success=False,
            numeric_id=numeric_id,
            last_chars=card["lastCharacters"],
            current_balance=f'{Decimal(card["balance"]["amount"]):.2f}',
            currency=card["balance"]["currencyCode"],
        )

    if action == "review":
        numeric_id = request.form["gift_card_id"]
        last_chars = request.form["last_chars"]
        current_balance = Decimal(request.form["current_balance"])
        currency = request.form["currency"]
        balance_action = request.form["balance_action"]

        try:
            amount = Decimal(request.form["amount"]).quantize(Decimal("0.01"))
        except InvalidOperation:
            return render_template_string(
                HTML,
                stage="lookup",
                error="Please enter a valid amount.",
                success=False,
            )

        if amount <= 0:
            return render_template_string(
                HTML,
                stage="lookup",
                error="Amount must be greater than $0.",
                success=False,
            )

        if balance_action == "subtract":
            if amount > current_balance:
                return render_template_string(
                    HTML,
                    stage="lookup",
                    error="Cannot subtract more than the current balance.",
                    success=False,
                )
            new_balance = current_balance - amount
        else:
            new_balance = current_balance + amount

        confirmation_token = secrets.token_urlsafe(16)
        
        return render_template_string(
                HTML,
                stage="confirm",
                error=None,
                success=False,
                numeric_id=numeric_id,
                last_chars=last_chars,
                current_balance=f"{current_balance:.2f}",
                amount=f"{amount:.2f}",
                new_balance=f"{new_balance:.2f}",
                currency=currency,
                balance_action=balance_action,
                confirmation_token=confirmation_token,       
     )

    if action == "credit":
        numeric_id = request.form["gift_card_id"]
        amount = Decimal(request.form["amount"])
        currency = request.form["currency"]
        confirmation_token = request.form["confirmation_token"]

        if confirmation_token in used_confirmations:
            return render_template_string(
                HTML,
                stage="lookup",
                error="This transaction was already submitted.",
                success=False,
            )

        used_confirmations.add(confirmation_token)
        gift_card_id = f"gid://shopify/GiftCard/{numeric_id}"

        result = credit_gift_card(
            token,
            gift_card_id,
            amount,
            currency,
        )

        if result.get("errors"):
            return render_template_string(
                HTML,
                stage="lookup",
                error=result["errors"][0]["message"],
                success=False,
            )

        credit_result = result["data"]["giftCardCredit"]

        if credit_result["userErrors"]:
            return render_template_string(
                HTML,
                stage="lookup",
                error=credit_result["userErrors"][0]["message"],
                success=False,
            )

        transaction = credit_result["giftCardCreditTransaction"]

        if not transaction:
            return render_template_string(
                HTML,
                stage="lookup",
                error="Shopify did not return a transaction.",
                success=False,
            )

        final_balance = Decimal(
            transaction["giftCard"]["balance"]["amount"]
        )

        return render_template_string(
            HTML,
            stage="done",
            error=None,
            success=True,
            added=f"{amount:.2f}",
            final_balance=f"{final_balance:.2f}",
            currency=currency,
            transaction_id=transaction["id"],
            balance_action="add",
        )

    if action == "debit":
        numeric_id = request.form["gift_card_id"]
        amount = Decimal(request.form["amount"])
        currency = request.form["currency"]
        confirmation_token = request.form["confirmation_token"]

        if confirmation_token in used_confirmations:
            return render_template_string(
                HTML,
                stage="lookup",
                error="This transaction was already submitted.",
                success=False,
            )

        used_confirmations.add(confirmation_token)
        gift_card_id = f"gid://shopify/GiftCard/{numeric_id}"

        result = debit_gift_card(
            token,
            gift_card_id,
            amount,
            currency,
        )

        if result.get("errors"):
            return render_template_string(
                HTML,
                stage="lookup",
                error=result["errors"][0]["message"],
                success=False,
            )

        debit_result = result["data"]["giftCardDebit"]

        if debit_result["userErrors"]:
            return render_template_string(
                HTML,
                stage="lookup",
                error=debit_result["userErrors"][0]["message"],
                success=False,
            )

        transaction = debit_result["giftCardDebitTransaction"]

        if not transaction:
            return render_template_string(
                HTML,
                stage="lookup",
                error="Shopify did not return a transaction.",
                success=False,
            )

        final_balance = Decimal(
            transaction["giftCard"]["balance"]["amount"]
        )

        return render_template_string(
            HTML,
            stage="done",
            error=None,
            success=True,
            added=f"{amount:.2f}",
            final_balance=f"{final_balance:.2f}",
            currency=currency,
            transaction_id=transaction["id"],
            balance_action="subtract",
        )

    return render_template_string(
        HTML,
        stage="lookup",
        error="Unknown action.",
        success=False,
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False
    )
