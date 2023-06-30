import azure.functions as func
import logging
import os
import json

import azure.functions as func
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import ImageDescription
from msrest.authentication import CognitiveServicesCredentials


app = func.FunctionApp()


# Clé de Azure Cognitive Services
VISION_SUBS_KEY = os.environ["VISION_SUBS_KEY"]
# Point d'accès à Azure Cognitive Services
VISION_ENDPOINT = os.environ["VISION_ENDPOINT"]


@app.function_name(name="negotiatev2")
@app.route(route="negotiatev2", auth_level=func.AuthLevel.ANONYMOUS)
@app.generic_input_binding(arg_name="connectionInfo", type="SignalRConnectionInfo", kwargs={
    "hubName": "serverless",
    "connectionStringSetting": os.environ["SIGNALR_CONNECTION_STRING"]
})
def negotiatev2(req: func.HttpRequest, connectionInfo) -> func.HttpResponse:
    """
    Permet à un client (navigateur web) de créer une connexion à Azure SignalR Service
    """
    logging.info('negotiate: fonction déclenchée')
    return func.HttpResponse(connectionInfo)


@app.function_name(name="getUploadedImagev2")
@app.event_grid_trigger(arg_name="event")
@app.cosmos_db_output(arg_name="doc", 
                      connection=os.environ["AZCOG_DATABASE_CONNECTION_STRING"],
                      database_name=os.environ["AZCOG_DATABASE_NAME"],
                      container_name=os.environ["AZCOG_COLLECTION_NAME"])
def getUploadedImagev2(event:func.EventGridEvent, doc:func.Out[func.Document]):
    """
    Permet d'analyser une image uploadée et ensuite d'enregistrer l'analyse dans une 
    base de données Cosmos DB
    """
    # 1. Récupération de l'url de l'image uploadée
    logging.info("getUploadedImage: function triggered")
    logging.info(f"{event.get_json()}")
    # Récupération de l'url de l'image uploadée dans Azure Blob Storage
    data = event.get_json()
    image_url = data["url"]

    #2. Analyse de l'image
    # Récupération du client Computer Vision
    vision_client = ComputerVisionClient(VISION_ENDPOINT, CognitiveServicesCredentials(VISION_SUBS_KEY))
    # Génération de la description
    image_description:ImageDescription = vision_client.describe_image(image_url)
    if (len(image_description.captions) == 0):
        logging.info("Pas de description détectée")
    else:
        for caption in image_description.captions:
            logging.info("Description: '{}' avec la probabilité: {}".format(caption.text, caption.confidence))

    # 3. Sauvegarde de la description dans la base de données
    document = {
        "image_url": image_url,
        "description": image_description.captions[0].text,
        "confidence": image_description.captions[0].confidence
    }

    doc.set(func.Document.from_dict(document))
    logging.info(f"Le document a bien été enregistré dans la base de donnée {document}")


@app.cosmos_db_trigger(arg_name="documents",
                       connection=os.environ["AZCOG_DATABASE_CONNECTION_STRING"],
                       database_name=os.environ["AZCOG_DATABASE_NAME"],
                       container_name=os.environ["AZCOG_COLLECTION_NAME"], 
                       lease_container_name="leases", 
                       create_lease_container_if_not_exists=True)
@app.generic_output_binding(arg_name="signalRMessages", 
                        type="signalR", 
                        kwargs={
                            "hubName": "serverless",
                            "connectionStringSetting": os.environ["SIGNALR_CONNECTION_STRING"]
                        })
def pushImageDescription(documents: func.DocumentList, signalRMessages: func.Out[str]):
    logging.info("pushImageDescription: fonction déclenchée")
    # Récupération de la liste de documents sous forme de chaîne de caractères
    doc_list = []
    for doc in documents:
        doc_list.append(json.dumps(doc.to_json()))

    # Envoi du document aux clients via SignalR
    signalRMessages.set(json.dumps({
        'target': 'newMessage',
        'arguments': doc_list
    }))
    logging.info(f"pushImageDescription: message SignalRMessage envoyé aux clients")


