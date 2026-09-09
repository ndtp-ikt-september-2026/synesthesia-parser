'''
Pydantic data models defining the instrument ingestion contract.
'''

from typing import List, Dict, Any
from pydantic import BaseModel, Field


class InstrumentPayload(BaseModel):
    '''
    Output data schema strictly compatible with OpenCart LiveStore ingestion CLI.
    '''
    type: str = Field(default='instrument', description='Entity type discriminator')
    name: str = Field(description='Human-readable instrument name')
    model: str = Field(description='Unique SKU / article from pop-music.ru')
    price: float = Field(default=0.0, description='Current price in BYN (converted from RUB / 25 and rounded)')
    quantity: int = Field(default=5, description='Available stock: 5 if in stock, 0 if out')
    category_ids: List[int] = Field(
        default_factory=list,
        description='Mapped OpenCart category IDs: [<subcategory_id>, <parent_category_id>] or [<parent_category_id>]'
    )
    image_url: str = Field(default='', description='Primary cover image URL')
    additional_images: List[str] = Field(default_factory=list, description='Secondary gallery image URLs')
    description: str = Field(default='', description='Clean textual description')
    attributes: Dict[str, str] = Field(default_factory=dict, description='Standardized attribute key-value map')
    text_for_embedding: str = Field(default='', description='Deterministic semantic prompt for vectorization')
    embedding: List[float] = Field(default_factory=list, description='384-dimensional unit-length float vector')
