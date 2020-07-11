from celery import shared_task
from celery.utils.log import get_task_logger

from charged.lninvoice.models import PurchaseOrderInvoice

logger = get_task_logger(__name__)


@shared_task()
def process_initial_lni(obj_id):
    logger.info('Running on ID: %s' % obj_id)

    # checks
    obj: PurchaseOrderInvoice = PurchaseOrderInvoice.objects \
        .filter(id=obj_id) \
        .filter(status=PurchaseOrderInvoice.INITIAL) \
        .first()

    if not obj:
        logger.info('Not found')
        return False

    if not obj.lnnode:
        logger.info('No backend: %s  - skipping' % obj)
        return False

    obj.lnnode_create_invoice()
    logger.info(f'New Payment Request: {obj.payment_request}')

    return True


class LnInvoiceNoPaymentError(Exception):
    pass


class LnInvoiceNotFoundError(Exception):
    pass


class LnInvoiceNoBackendError(Exception):
    pass


@shared_task(bind=True,
             autoretry_for=(LnInvoiceNoPaymentError,),
             default_retry_delay=5,
             retry_kwargs={'max_retries': 180},
             retry_backoff=False,
             retry_backoff_max=60,
             retry_jitter=True)
def check_lni_for_successful_payment(self, obj_id):
    logger.info('Running on ID: %s' % obj_id)

    # checks
    obj: PurchaseOrderInvoice = PurchaseOrderInvoice.objects \
        .filter(id=obj_id) \
        .filter(status=PurchaseOrderInvoice.UNPAID) \
        .first()

    if not obj:
        logger.info('Not found')
        raise LnInvoiceNotFoundError()

    if not obj.lnnode:
        logger.info('No backend: %s  - skipping' % obj)
        raise LnInvoiceNoBackendError

    obj.lnnode_sync_invoice()

    if obj.status == PurchaseOrderInvoice.PAID:
        logger.info('PAID!')
    else:
        if not obj.has_expired:
            # enqueue for another check later on
            raise LnInvoiceNoPaymentError()
