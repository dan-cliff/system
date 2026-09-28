def migrate(cr, version):
    """Food and Quantity per Feed became one Food Required text: put the quantity in front of the food."""
    for table in ('kennel_diet', 'kennel_booking_line'):
        cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = 'quantity'", [table])
        if cr.fetchone():
            cr.execute(f"""
                UPDATE {table}
                   SET food = NULLIF(CONCAT_WS(' ', NULLIF(quantity, ''), NULLIF(food, '')), '')
                 WHERE COALESCE(quantity, '') != ''
            """)
