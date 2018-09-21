/*
 * Copyright 2017-2018 AVSystem <avsystem@avsystem.com>
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#ifndef ANJAY_SERVERS_SERVER_CONNECTIONS_H
#define ANJAY_SERVERS_SERVER_CONNECTIONS_H

#include "../anjay_core.h"
#include "../utils_core.h"

#if !defined(ANJAY_SERVERS_INTERNALS) && !defined(ANJAY_TEST)
#    error "Headers from servers/ are not meant to be included from outside"
#endif

#include "connections.h"
#include "servers_internal.h"

VISIBILITY_PRIVATE_HEADER_BEGIN

static inline anjay_server_connection_t *
_anjay_get_server_connection(anjay_connection_ref_t ref) {
    return _anjay_connection_get(&ref.server->connections, ref.conn_type);
}

/**
 * @returns @li 0 on success,
 *          @li a positive errno value in case of a primary socket (UDP) error,
 *          @li a negative value in case of other error.
 */
int _anjay_active_server_refresh(anjay_t *anjay, anjay_server_info_t *server);

VISIBILITY_PRIVATE_HEADER_END

#endif // ANJAY_SERVERS_SERVER_CONNECTIONS_H
