"""Genera el código TOTP de 6 dígitos del usuario demo (equivale a la app autenticadora)."""
import sys
import pyotp
print(pyotp.TOTP(sys.argv[1] if len(sys.argv) > 1 else "JBSWY3DPEHPK3PXP").now())
