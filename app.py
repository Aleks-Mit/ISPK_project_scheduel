# app.py – paleidimo failas. Visa logika yra kituose moduliuose.

from core import app

# Šių modulių importavimas užregistruoja jų maršrutus
import routes_auth       # noqa: F401
import routes_schedule   # noqa: F401
import routes_requests   # noqa: F401
import routes_admin      # noqa: F401
import routes_messages   # noqa: F401
import routes_hr         # noqa: F401
import routes_shifts     # noqa: F401

if __name__ == "__main__":
    app.run(debug=True)