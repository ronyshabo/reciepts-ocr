# Firebase Setup Instructions

## Step 1: Download Service Account Key

1. Go to Firebase Console: https://console.firebase.google.com/project/receipts-ocr-3381a/settings/serviceaccounts/adminsdk

2. Click "Generate new private key"

3. Save the downloaded JSON file as `serviceAccountKey.json` in your project root directory:
   ```
   /home/ray8reaper/Desktop/Recipt_app/receipt-processor-app/serviceAccountKey.json
   ```

## Step 2: Firestore Database Setup

1. Go to: https://console.firebase.google.com/project/receipts-ocr-3381a/firestore

2. Create a Firestore database if you haven't already

3. Set up the following collection structure:
   ```
   receipts/
   ├── [document_id]/
       ├── store: {
       │   ├── name: string
       │   ├── location: string
       │   ├── phone: string
       │   ├── pharmacy_phone: string
       │   └── store_hours: string
       │   }
       ├── receipt: {
       │   ├── date: string
       │   ├── time: string
       │   ├── cashier: string
       │   ├── receipt_id: string
       │   └── expires: string
       │   }
       ├── items: [
       │   {
       │   ├── name: string
       │   ├── quantity: number
       │   ├── unit_price: number
       │   └── total: number
       │   }
       │   ]
       ├── summary: {
       │   ├── items_purchased: number
       │   ├── subtotal: number
       │   ├── savings: number
       │   └── total: number
       │   }
       ├── payment: {
       │   ├── method: string
       │   ├── card_type: string
       │   ├── last4: string
       │   ├── amount: number
       │   ├── transaction_id: string
       │   └── ref_no: string
       │   }
       └── metadata: {
           ├── created_at: timestamp
           ├── processed_by: string
           └── raw_ocr_text: string
           }
   ```

## Step 3: Security Rules (Optional)

Set up basic security rules in Firestore:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Allow read/write access to receipts collection
    match /receipts/{document} {
      allow read, write: if true; // For development - restrict in production
    }
  }
}
```

## Step 4: Test Connection

After placing the service account key file, restart your Flask app and test uploading a receipt.