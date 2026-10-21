# Embroidery Submissions

Price embroidery from a submitted design file. Works like the 3D Print
Calculator, but for Brother `.pes` embroidery files.

## What it reads

When a `.pes` file is submitted (in Odoo or on the website), it is read with
Embroidery Jobbing's PES reader:

* stitch count
* thread colours (name, colour and stitches of each)
* colour changes, trims and jumps
* size (mm) and a stitch preview

A note is added when the design is larger than every hoop under
**Embroidery › Configuration › Hoops & Frames**.

## Estimated time

```
duration = stitches ÷ stitches per minute
         + colour changes × time per colour change   (pricing profile)
         + hooping time per piece                     (pricing profile)
```

The stitches per minute come from **Settings › Embroidery › Submission
Defaults › Estimate duration based on stitches** (600 by default). Each
submission records the speed it was estimated with. Changing the setting
does not change prices already quoted; **Update Pricing** on a submission
re-estimates it with the current setting.

## Costing

From the submission's pricing profile (**Embroidery › Configuration ›
Pricing Profiles**):

| Cost | Worked out as |
| --- | --- |
| Stitch Cost | stitches ÷ 1,000 × Cost per 1,000 Stitches |
| Colour Change Fees | colour changes × Fee per Colour Change |
| Machine Time Cost | estimated hours × Machine Rate per Hour |
| Setup Fee | once per piece |
| Price per Piece | total cost + Markup (%), never below the Minimum Price |

The profile comes from the product, else the company default (Settings), else
the first profile.

## Selling it

* Products with **Embroidery Dynamic Pricing** (Product › Embroidery tab)
  are priced from the submission on the sales order line. The product
  "Custom Embroidery" is set up for this.
* **Create Quotation** on a submission starts a quotation for it.
* Confirming the order creates an **Embroidery Job** for each submission,
  with the design added to the design library and the ordered quantity as
  pieces. **Create Job** on a submission does the same by hand.
* Invoices record the costing (Embroidery Costings tab). Once invoiced, a
  submission's file and costing are locked.

## Website

Customers upload their `.pes` file on the product page of a dynamically
priced product, or at `/shop/embroidery-quote`, and see the stitches,
colours, colour changes, size, estimated time per piece and the price before
adding it to their cart. Uploads that never reach a cart are removed after
7 days. The upload limit is set in Settings (10 MB by default).
